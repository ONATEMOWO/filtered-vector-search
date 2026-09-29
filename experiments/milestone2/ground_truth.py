"""Durable exact ground truth and independent NumPy validation."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import psycopg

from .config import canonical_json_bytes
from .database import EXACT_TABLE


def ground_truth_sql(threshold: int, k: int) -> str:
    if threshold not in {1, 5, 10, 20, 50}:
        raise ValueError("filter threshold is not part of the frozen protocol")
    return (
        f"SELECT id, embedding <-> %s::vector AS distance FROM {EXACT_TABLE} "
        f"WHERE filter_bucket < {threshold} ORDER BY distance "
        f"FETCH FIRST {k} ROWS WITH TIES"
    )


def make_ground_truth_record(
    *,
    run_id: str,
    scale_rows: int,
    threshold: int,
    qualifying_count: int,
    query_id: int,
    k: int,
    rows: Iterable[tuple[int, float]],
    dataset_sha256: str,
    scale_manifest_sha256: str,
) -> dict[str, Any]:
    all_rows = [(int(identifier), float(distance)) for identifier, distance in rows]
    if len(all_rows) < k:
        raise ValueError(f"exact ground truth returned {len(all_rows)} rows, expected at least {k}")
    ordered = sorted(all_rows, key=lambda value: (value[1], value[0]))
    canonical = ordered[:k]
    boundary_distance = canonical[-1][1]
    closer = [identifier for identifier, distance in ordered if distance < boundary_distance]
    ties = [identifier for identifier, distance in ordered if distance == boundary_distance]
    if len(closer) >= k or len(closer) + len(ties) < k:
        raise AssertionError("invalid exact boundary-tie partition")
    record: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "generation_method": (
            "PostgreSQL exact filtered L2 search on milestone2.sift_exact "
            "with no vector index"
        ),
        "generation_sql": ground_truth_sql(threshold, k),
        "dataset_sha256": dataset_sha256,
        "scale_manifest_sha256": scale_manifest_sha256,
        "scale_rows": scale_rows,
        "filter_threshold": threshold,
        "qualifying_count": qualifying_count,
        "query_id": query_id,
        "k": k,
        "canonical_ids": [identifier for identifier, _ in canonical],
        "canonical_distances": [distance for _, distance in canonical],
        "boundary_distance": boundary_distance,
        "strictly_closer_ids": closer,
        "boundary_tie_ids": ties,
        "all_with_ties_ids": [identifier for identifier, _ in ordered],
        "all_with_ties_distances": [distance for _, distance in ordered],
    }
    record["record_sha256"] = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return record


def generate_ground_truth(
    connection: psycopg.Connection[Any],
    *,
    run_id: str,
    scale_rows: int,
    thresholds: Iterable[int],
    qualifying_counts: Mapping[int, int],
    query_ids: Iterable[int],
    query_vectors: Mapping[int, np.ndarray],
    k: int,
    dataset_sha256: str,
    scale_manifest_sha256: str,
) -> tuple[list[dict[str, Any]], int]:
    started = time.perf_counter_ns()
    records: list[dict[str, Any]] = []
    with connection.cursor() as cursor:
        for query_id in query_ids:
            vector = query_vectors[int(query_id)]
            for threshold in thresholds:
                statement = ground_truth_sql(int(threshold), k)
                cursor.execute(statement, (vector,), prepare=True)
                rows = [(int(row[0]), float(row[1])) for row in cursor.fetchall()]
                records.append(
                    make_ground_truth_record(
                        run_id=run_id,
                        scale_rows=scale_rows,
                        threshold=int(threshold),
                        qualifying_count=int(qualifying_counts[int(threshold)]),
                        query_id=int(query_id),
                        k=k,
                        rows=rows,
                        dataset_sha256=dataset_sha256,
                        scale_manifest_sha256=scale_manifest_sha256,
                    )
                )
    return records, time.perf_counter_ns() - started


def ground_truth_index(records: Iterable[dict[str, Any]]) -> dict[tuple[int, int], dict[str, Any]]:
    index: dict[tuple[int, int], dict[str, Any]] = {}
    for record in records:
        without_checksum = {key: value for key, value in record.items() if key != "record_sha256"}
        observed = hashlib.sha256(canonical_json_bytes(without_checksum)).hexdigest()
        if observed != record["record_sha256"]:
            raise ValueError("ground-truth record checksum mismatch")
        key = (int(record["query_id"]), int(record["filter_threshold"]))
        if key in index:
            raise ValueError(f"duplicate ground-truth key {key}")
        index[key] = record
    return index


def select_validation_keys(
    query_ids: Iterable[int], thresholds: Iterable[int], count: int
) -> list[tuple[int, int]]:
    queries = [int(query_id) for query_id in query_ids]
    filters = [int(threshold) for threshold in thresholds]
    if count < 0:
        raise ValueError("validation count cannot be negative")
    if len(queries) != len(set(queries)) or len(filters) != len(set(filters)):
        raise ValueError("validation queries and thresholds must be unique")
    if count > len(queries) * len(filters):
        raise ValueError("validation count exceeds the available combinations")

    # Round-robin across independently hashed per-filter query orders. A sample
    # of at least one key per filter is therefore explicitly stratified.
    candidates: dict[int, list[tuple[int, int]]] = {}
    for threshold in filters:
        keys = [(query_id, threshold) for query_id in queries]
        keys.sort(
            key=lambda value: (
                hashlib.sha256(
                    f"sift-gt-validation-v1|{value[0]}|{value[1]}".encode("utf-8")
                ).digest(),
                value,
            )
        )
        candidates[threshold] = keys

    selected: list[tuple[int, int]] = []
    depth = 0
    while len(selected) < count:
        made_progress = False
        for threshold in filters:
            if depth < len(candidates[threshold]):
                selected.append(candidates[threshold][depth])
                made_progress = True
                if len(selected) == count:
                    break
        if not made_progress:
            break
        depth += 1
    return selected


def validate_ground_truth_numpy(
    *,
    records: Mapping[tuple[int, int], dict[str, Any]],
    validation_keys: Iterable[tuple[int, int]],
    base_ids: np.ndarray,
    vectors: np.ndarray,
    buckets: np.ndarray,
    query_vectors: Mapping[int, np.ndarray],
    k: int,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    base_ids = np.asarray(base_ids, dtype=np.int32)
    vectors64 = np.asarray(vectors, dtype=np.float64)
    for query_id, threshold in validation_keys:
        mask = np.asarray(buckets) < int(threshold)
        eligible_ids = base_ids[mask]
        eligible_vectors = vectors64[mask]
        query = np.asarray(query_vectors[int(query_id)], dtype=np.float64)
        squared = np.sum((eligible_vectors - query) ** 2, axis=1, dtype=np.float64)
        ordering = np.lexsort((eligible_ids, squared))
        expected_ids = [int(value) for value in eligible_ids[ordering[:k]]]
        expected_distances = np.sqrt(squared[ordering[:k]])
        record = records[(int(query_id), int(threshold))]
        if expected_ids != [int(value) for value in record["canonical_ids"]]:
            raise AssertionError(
                f"NumPy ground truth differs for query={query_id}, threshold={threshold}: "
                f"expected {expected_ids}, PostgreSQL {record['canonical_ids']}"
            )
        observed_distances = np.asarray(record["canonical_distances"], dtype=np.float64)
        if not np.allclose(expected_distances, observed_distances, rtol=2e-6, atol=2e-5):
            raise AssertionError(
                f"NumPy distances differ for query={query_id}, threshold={threshold}"
            )
        if int(record["qualifying_count"]) != int(np.count_nonzero(mask)):
            raise AssertionError("NumPy qualifying count differs from PostgreSQL ground truth")
        checks.append(
            {
                "query_id": query_id,
                "filter_threshold": threshold,
                "canonical_ids_match": True,
                "distance_tolerance_rtol": 2e-6,
                "distance_tolerance_atol": 2e-5,
                "qualifying_count_match": True,
            }
        )
    return {
        "implementation": "independent NumPy float64 brute force over the physical scale",
        "validated_combination_count": len(checks),
        "checks": checks,
        "passed": True,
    }
