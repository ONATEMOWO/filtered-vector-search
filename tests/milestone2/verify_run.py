#!/usr/bin/env python3
"""Independently verify a completed Milestone 2 qualification run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiments.milestone2.artifacts import verify_checksum_manifest  # noqa: E402
from experiments.milestone2.config import (  # noqa: E402
    BenchmarkConfig,
    PROTOCOL_PATH,
    read_json as read_config_json,
    sha256_json,
    validate_config,
)
from experiments.milestone2.dataset import (  # noqa: E402
    build_scale_manifest,
    deterministic_id_order,
    load_query_vectors,
    load_scale_vectors,
    select_query_ids,
    validate_hdf5,
    validate_source_manifest_identity,
)
from experiments.milestone2.database import search_sql, source_stream_checksum  # noqa: E402
from experiments.milestone2.ground_truth import (  # noqa: E402
    ground_truth_index,
    ground_truth_sql,
    make_ground_truth_record,
    select_validation_keys,
    validate_ground_truth_numpy,
)
from experiments.milestone2.metrics import (  # noqa: E402
    canonical_recall_at_k,
    tie_aware_recall_at_k,
    validate_returned_results,
)
from experiments.milestone2.plans import verify_plan_document  # noqa: E402
from experiments.milestone2.runner import build_schedule  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def verify_query_selection(manifest: dict[str, Any], stage: dict[str, Any]) -> None:
    expected = select_query_ids()
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise AssertionError("query selection differs from deterministic reconstruction")
    if manifest.get("qualification_timed_query_ids") != expected["measured_query_ids"][: int(stage["timed_query_count"])]:
        raise AssertionError("timed query IDs are not the declared deterministic prefix")


def verify_result_fields(
    row: dict[str, Any], selected_buckets: dict[int, int], threshold: int, k: int
) -> None:
    ids = [int(value) for value in row["result_ids"]]
    distances = [float(value) for value in row["distances"]]
    if not all(math.isfinite(value) and value >= 0 for value in distances):
        raise AssertionError("result contains invalid L2 distances")
    actual = validate_returned_results(
        ids, distances, k=k, selected_buckets=selected_buckets, threshold=threshold
    )
    if not all(actual[name] for name in ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")):
        raise AssertionError("returned result rows fail independent validation")
    for name, value in actual.items():
        if row.get(name) != value or (isinstance(value, bool) and type(row.get(name)) is not bool):
            raise AssertionError(f"stored {name} differs from result rows")


def verify_source_distances(
    row: dict[str, Any], query: np.ndarray, vectors: np.ndarray, id_to_position: dict[int, int]
) -> None:
    positions = [id_to_position[int(identifier)] for identifier in row["result_ids"]]
    if not positions:
        return
    selected = np.asarray(vectors[positions], dtype=np.float64)
    expected = np.sqrt(np.sum((selected - np.asarray(query, dtype=np.float64)) ** 2, axis=1))
    if not np.allclose(expected, row["distances"], rtol=2e-6, atol=2e-5):
        raise AssertionError("returned distances differ from canonical source-vector L2")


def independent_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recompute query-level reductions without calling the producer summary."""
    conditions: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        conditions[(row["method"], row["filter_threshold"])].append(row)
    result = []
    for (method, threshold), records in sorted(conditions.items()):
        queries: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            if record["error_type"] is None:
                queries[int(record["query_id"])].append(record)
        latencies = sorted(int(statistics.median(record["duration_ns"] for record in group)) for group in queries.values())
        rank = (len(latencies) - 1) * 0.95
        lo, hi = math.floor(rank), math.ceil(rank)
        percentile = latencies[lo] + (latencies[hi] - latencies[lo]) * (rank - lo)
        result.append({
            "method": method,
            "filter_threshold": threshold,
            "execution_samples": len(records),
            "successful_executions": sum(len(group) for group in queries.values()),
            "query_samples": len(queries),
            "repetition_reduction": "median latency per query before condition summary",
            "median_latency_ns": int(statistics.median(latencies)),
            "minimum_query_median_latency_ns": min(latencies),
            "maximum_query_median_latency_ns": max(latencies),
            "p95_query_median_latency_ns": int(percentile),
            "mean_canonical_recall_at_10": statistics.fmean(statistics.fmean(record["canonical_recall_at_10"] for record in group) for group in queries.values()),
            "mean_tie_aware_recall_at_10": statistics.fmean(statistics.fmean(record["tie_aware_recall_at_10"] for record in group) for group in queries.values()),
            "returned_k_rate": sum(record["returned_k"] for record in records) / len(records),
        })
    return result


def verify_summary(stored: list[dict[str, Any]], executions: list[dict[str, Any]]) -> None:
    expected = independent_summary(executions)
    if len(stored) != len(expected):
        raise AssertionError("summary condition count differs from execution rows")
    for actual, recomputed in zip(stored, expected, strict=True):
        if actual.keys() != recomputed.keys():
            raise AssertionError("summary fields differ from independent recomputation")
        for name, value in recomputed.items():
            if name == "p95_query_median_latency_ns":
                # NumPy interpolates from the upper endpoint for fractions >= .5;
                # our independent formula uses the lower endpoint. Floating-point
                # roundoff followed by integer truncation can differ by one ns.
                if type(actual[name]) is not int or abs(actual[name] - value) > 1:
                    raise AssertionError("summary p95 differs beyond 1 ns interpolation tolerance")
            elif actual[name] != value:
                raise AssertionError(f"summary {name} differs from independent recomputation")


def verify_run(run_dir: Path) -> dict[str, object]:
    required = {
        "config.json",
        "run_manifest.json",
        "dataset_manifest.json",
        "environment.json",
        "power_state.json",
        "postgres_settings.json",
        "method_sessions.json",
        "prepared_statements.json",
        "queries.json",
        "schedule.json",
        "scale_manifest.json",
        "filter_counts.json",
        "ground_truth.jsonl",
        "ground_truth_reexecution.json",
        "ground_truth_validation.json",
        "executions.jsonl",
        "warmups.jsonl",
        "plan_assertions.jsonl",
        "database_evidence.json",
        "relation_sizes.json",
        "source_vector_samples.json",
        "summary.json",
        "cache_reset.json",
        "phase_metrics.json",
        "resource_observations.json",
        "validation_report.json",
        "checksums.sha256",
        "COMPLETE.json",
    }
    missing = sorted(name for name in required if not (run_dir / name).is_file())
    if missing:
        raise AssertionError(f"missing required run artifacts: {missing}")
    if (run_dir / "INVALID.json").exists():
        raise AssertionError("run contains INVALID.json")
    if (run_dir / "ACTIVE").exists():
        raise AssertionError("completed run still contains ACTIVE marker")
    verify_checksum_manifest(run_dir)

    resolved = read_json(run_dir / "config.json")
    protocol = resolved["protocol"]
    stage = resolved["stage"]
    validate_config(protocol, stage)
    committed_protocol = read_config_json(PROTOCOL_PATH)
    committed_stage_path = (
        ROOT / "config" / "milestone2" / f"{stage['stage_id']}.json"
    )
    if protocol != committed_protocol or stage != read_config_json(committed_stage_path):
        raise AssertionError("embedded run configuration differs from committed source of truth")
    config_sha256 = sha256_json(resolved)
    benchmark_config = BenchmarkConfig(
        protocol=protocol,
        stage=stage,
        combined=resolved,
        config_sha256=config_sha256,
        source_path=committed_stage_path,
    )
    if not run_dir.name.endswith(f"_{config_sha256[:12]}"):
        raise AssertionError("run ID does not contain the resolved configuration digest")
    run_manifest = read_json(run_dir / "run_manifest.json")
    complete = read_json(run_dir / "COMPLETE.json")
    if (
        run_manifest.get("run_id") != run_dir.name
        or complete.get("run_id") != run_dir.name
        or run_manifest.get("config_sha256") != config_sha256
        or not complete.get("valid")
    ):
        raise AssertionError("run/config/final marker identities are inconsistent")
    git_at_start = run_manifest.get("git_at_start", {})
    if git_at_start.get("dirty") or git_at_start.get("status_porcelain"):
        raise AssertionError("run did not start from a clean Git state")
    source_commit = str(git_at_start.get("commit", ""))
    if len(source_commit) != 40 or any(character not in "0123456789abcdef" for character in source_commit):
        raise AssertionError("run lacks a full source commit identity")
    for path, expected_config in (("config/milestone2/protocol.json", protocol), (f"config/milestone2/{stage['stage_id']}.json", stage)):
        committed = subprocess.run(
            ["git", "show", f"{source_commit}:{path}"], cwd=ROOT,
            text=True, capture_output=True, check=True,
        )
        if json.loads(committed.stdout) != expected_config:
            raise AssertionError("run configuration differs from its recorded source commit")

    filters = [int(value) for value in protocol["filter_thresholds"]]
    methods = [str(value) for value in protocol["methods"]]
    k = int(protocol["k"])
    scale_rows = int(stage["scale_rows"])
    versions = read_json(run_dir / "environment.json").get("database_versions", {})
    if versions.get("postgresql_version") != protocol["postgresql_version"] or versions.get("pgvector_version") != protocol["pgvector_version"] or versions.get("postgresql_version_num") != "170011":
        raise AssertionError("recorded PostgreSQL/pgvector versions differ from protocol")

    dataset_manifest = read_json(run_dir / "dataset_manifest.json")
    dataset_protocol = protocol["dataset"]
    if (
        dataset_manifest.get("sha256") != dataset_protocol["expected_sha256"]
        or int(dataset_manifest.get("byte_size", -1)) != dataset_protocol["expected_bytes"]
        or not dataset_manifest.get("validation_passed")
    ):
        raise AssertionError("dataset identity or validation evidence is invalid")
    if not dataset_manifest.get("source_manifest_identity_validation", {}).get("passed"):
        raise AssertionError("source manifest was not cross-checked against the protocol")
    source_validation = validate_source_manifest_identity(dataset_manifest["canonical_source"], dataset_protocol)
    if dataset_manifest["source_manifest_identity_validation"] != source_validation:
        raise AssertionError("source manifest identity evidence does not recompute")
    dataset_path = ROOT / dataset_protocol["local_path"]
    observed_dataset = validate_hdf5(dataset_path, expected_sha256=dataset_protocol["expected_sha256"])
    for name in ("sha256", "byte_size", "groups", "attributes", "zero_based_sentinel", "values_normalized", "base_ids_zero_based"):
        if dataset_manifest.get(name) != observed_dataset[name]:
            raise AssertionError(f"dataset {name} differs from independently inspected source")
    power = read_json(run_dir / "power_state.json")
    if not power.get("ac_power_detected"):
        raise AssertionError("AC-power qualification gate did not pass")

    scale_manifest = read_json(run_dir / "scale_manifest.json")
    assignment = protocol["scale_assignment"]
    # Reconstruct independently in memory; never create or rewrite a runtime cache.
    global_order = deterministic_id_order(int(assignment["base_count"]), "sift-base-v1|")
    order_sha256 = hashlib.sha256(global_order.astype("<i4").tobytes()).hexdigest()
    if order_sha256 != assignment["expected_ordered_ids_sha256"]:
        raise AssertionError("deterministic global scale order differs from pinned identity")
    expected_scale = build_scale_manifest(global_order, scale_rows, filters)
    for name in ("selected_base_ids_sha256", "membership_sha256", "filter_counts"):
        if scale_manifest.get(name) != expected_scale[name]:
            raise AssertionError(f"scale manifest {name} differs from deterministic reconstruction")
    for name, expected_digest in (("cache_sha256", assignment["expected_cache_sha256"]), ("ordered_ids_sha256", order_sha256)):
        if scale_manifest.get("global_order", {}).get(name) != expected_digest:
            raise AssertionError(f"global scale-order {name} is inconsistent")
    scale_sha256 = sha256_json({name: value for name, value in scale_manifest.items() if name != "scale_manifest_sha256"})
    if scale_manifest.get("scale_manifest_sha256") != scale_sha256:
        raise AssertionError("scale manifest digest does not recompute")
    filter_counts = read_json(run_dir / "filter_counts.json")
    if filter_counts != expected_scale["filter_counts"] or filter_counts != stage["expected_filter_counts"]:
        raise AssertionError("filter counts differ from scale construction/configuration")
    selected_buckets = {
        int(identifier): int(bucket)
        for identifier, bucket in zip(
            expected_scale["selected_base_ids"],
            expected_scale["filter_buckets"],
            strict=True,
        )
    }

    query_manifest = read_json(run_dir / "queries.json")
    verify_query_selection(query_manifest, stage)
    timed_queries = [int(value) for value in query_manifest["qualification_timed_query_ids"]]
    measured_queries = [int(value) for value in query_manifest["measured_query_ids"]]
    warmup_queries = [int(value) for value in query_manifest["warmup_query_ids"]]
    if (
        len(measured_queries) != 200
        or len(warmup_queries) != 20
        or set(measured_queries).intersection(warmup_queries)
        or timed_queries != measured_queries[: int(stage["timed_query_count"])]
    ):
        raise AssertionError("query selection/count/disjointness evidence is invalid")
    query_vectors = load_query_vectors(dataset_path, measured_queries + warmup_queries)
    expected_vector_hashes = {
        str(query_id): hashlib.sha256(np.asarray(vector, dtype="<f4").tobytes()).hexdigest()
        for query_id, vector in query_vectors.items()
    }
    if query_manifest.get("vector_sha256") != expected_vector_hashes:
        raise AssertionError("query-vector checksums differ from canonical SIFT source")

    ground_truth_rows = read_jsonl(run_dir / "ground_truth.jsonl")
    ground_truth = ground_truth_index(ground_truth_rows)
    expected_ground_truth = int(stage["ground_truth_query_count"]) * len(filters)
    if len(ground_truth) != expected_ground_truth:
        raise AssertionError("ground-truth matrix is incomplete")
    expected_gt_keys = {(query_id, threshold) for query_id in measured_queries for threshold in filters}
    if set(ground_truth) != expected_gt_keys:
        raise AssertionError("ground-truth key matrix differs from the predetermined queries")
    for (query_id, threshold), record in ground_truth.items():
        if (
            record.get("generation_sql") != ground_truth_sql(threshold, k)
            or "PostgreSQL exact filtered L2" not in str(record.get("generation_method"))
            or int(record["scale_rows"]) != scale_rows
            or int(record["qualifying_count"]) != int(filter_counts[str(threshold)])
            or record["dataset_sha256"] != dataset_manifest["sha256"]
            or record.get("scale_manifest_sha256") != scale_sha256
            or record.get("run_id") != run_dir.name
            or record.get("k") != k
        ):
            raise AssertionError(f"ground-truth provenance differs for {(query_id, threshold)}")
        all_ids = record["all_with_ties_ids"]
        all_distances = record["all_with_ties_distances"]
        if len(all_ids) != len(all_distances) or len(all_ids) != len(set(all_ids)) or not all(math.isfinite(value) and value >= 0 for value in all_distances):
            raise AssertionError("ground-truth rows have invalid IDs or distances")
        if any(identifier not in selected_buckets or selected_buckets[identifier] >= threshold for identifier in all_ids):
            raise AssertionError("ground truth includes an out-of-scale/filter row")
        rebuilt = make_ground_truth_record(
            run_id=run_dir.name, scale_rows=scale_rows, threshold=threshold,
            qualifying_count=filter_counts[str(threshold)], query_id=query_id, k=k,
            rows=zip(all_ids, all_distances, strict=True),
            dataset_sha256=dataset_manifest["sha256"], scale_manifest_sha256=scale_sha256,
        )
        if rebuilt != record or any(distance > record["boundary_distance"] for distance in all_distances):
            raise AssertionError("ground-truth canonical ranking or tie partition is inconsistent")
    reexecution = read_json(run_dir / "ground_truth_reexecution.json")
    if (
        not reexecution.get("passed")
        or not reexecution.get("record_checksums_identical_in_order")
        or int(reexecution.get("reexecuted_records", 0)) != expected_ground_truth
    ):
        raise AssertionError("ground-truth deterministic re-execution is incomplete or failed")
    independent = read_json(run_dir / "ground_truth_validation.json")
    independent_checks = independent.get("checks", [])
    threshold_counts = {
        threshold: sum(
            int(check["filter_threshold"]) == threshold for check in independent_checks
        )
        for threshold in filters
    }
    if (
        not independent.get("passed")
        or int(independent.get("validated_combination_count", 0))
        < int(stage["independent_validation_count"])
        or min(threshold_counts.values(), default=0) == 0
        or max(threshold_counts.values(), default=0)
        - min(threshold_counts.values(), default=0)
        > 1
    ):
        raise AssertionError("independent ground-truth validation is not stratified/complete")
    validation_keys = select_validation_keys(measured_queries, filters, int(stage["independent_validation_count"]))
    vectors = load_scale_vectors(dataset_path, expected_scale["selected_base_ids"])
    id_to_position = {int(identifier): position for position, identifier in enumerate(expected_scale["selected_base_ids"])}
    repeated_independent = validate_ground_truth_numpy(
        records=ground_truth, validation_keys=validation_keys,
        base_ids=expected_scale["selected_base_ids"], vectors=vectors,
        buckets=expected_scale["filter_buckets"], query_vectors=query_vectors, k=k,
    )
    if independent != repeated_independent:
        raise AssertionError("independent validation evidence differs from repeated source calculation")

    executions = read_jsonl(run_dir / "executions.jsonl")
    method_sessions = read_json(run_dir / "method_sessions.json")
    backend_pids = method_sessions.get("backend_pids", {})
    if set(backend_pids) != set(methods) or len(set(backend_pids.values())) != len(methods):
        raise AssertionError("methods do not have distinct persistent backend identities")
    expected_execution_count = (
        len(methods)
        * len(filters)
        * len(timed_queries)
        * int(stage["repetitions"])
        * int(stage["rounds"])
    )
    if len(executions) != expected_execution_count:
        raise AssertionError(
            f"expected {expected_execution_count} executions, found {len(executions)}"
        )
    expected_keys = {
        (round_number, method, threshold, query_id, repetition)
        for round_number in range(1, int(stage["rounds"]) + 1)
        for method in methods
        for threshold in filters
        for query_id in timed_queries
        for repetition in range(1, int(stage["repetitions"]) + 1)
    }
    observed_keys: set[tuple[int, str, int, int, int]] = set()
    for row in executions:
        key = (
            int(row["round"]),
            str(row["method"]),
            int(row["filter_threshold"]),
            int(row["query_id"]),
            int(row["repetition"]),
        )
        if key in observed_keys:
            raise AssertionError(f"duplicate execution key {key}")
        observed_keys.add(key)
        if row["error_type"] is not None or row.get("error_message") is not None or row.get("timeout") is not False or type(row["duration_ns"]) is not int or row["duration_ns"] <= 0:
            raise AssertionError(f"failed/invalid timed execution {key}")
        expected_provenance = {
            "run_id": run_dir.name, "config_sha256": config_sha256,
            "stage_id": stage["stage_id"], "scale_rows": scale_rows,
            "build_id": f"{run_dir.name}-round-{key[0]}-build-1",
            "k": k, "backend_pid": backend_pids[key[1]], "prepared": True,
            "target_selectivity": key[2] / 100,
            "qualifying_count": filter_counts[str(key[2])],
            "logical_prepared_statement": f"{key[1]}_filter_{key[2]}",
            "sql_sha256": hashlib.sha256(search_sql(key[1], key[2], k).encode()).hexdigest(),
        }
        if any(row.get(name) != value for name, value in expected_provenance.items()):
            raise AssertionError(f"execution provenance differs for {key}")
        verify_result_fields(row, selected_buckets, key[2], k)
        verify_source_distances(row, query_vectors[key[3]], vectors, id_to_position)
        if not all(
            bool(row[name])
            for name in ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")
        ):
            raise AssertionError(f"result validation failure {key}")
        ids = [int(value) for value in row["result_ids"]]
        distances = [float(value) for value in row["distances"]]
        if not all(math.isfinite(value) for value in distances):
            raise AssertionError(f"non-finite result distance {key}")
        independently_validated = validate_returned_results(
            ids,
            distances,
            k=k,
            selected_buckets=selected_buckets,
            threshold=key[2],
        )
        for name, value in independently_validated.items():
            if row.get(name) != value:
                raise AssertionError(f"stored {name} differs from result rows for {key}")
        truth = ground_truth[(key[3], key[2])]
        if row.get("ground_truth_record_sha256") != truth["record_sha256"]:
            raise AssertionError(f"ground-truth reference mismatch {key}")
        canonical = canonical_recall_at_k(row["result_ids"], truth["canonical_ids"], k)
        tied = tie_aware_recall_at_k(
            row["result_ids"],
            truth["strictly_closer_ids"],
            truth["boundary_tie_ids"],
            k,
        )
        if not math.isclose(canonical, float(row["canonical_recall_at_10"]), abs_tol=1e-15):
            raise AssertionError(f"canonical recall mismatch {key}")
        if not math.isclose(tied, float(row["tie_aware_recall_at_10"]), abs_tol=1e-15):
            raise AssertionError(f"tie-aware recall mismatch {key}")
        if key[1] == "exact" and (
            canonical != 1.0 or tied != 1.0 or not bool(row["returned_k"])
        ):
            raise AssertionError(f"exact result is not complete ground truth {key}")
    if observed_keys != expected_keys:
        raise AssertionError("execution key matrix differs from configuration")

    schedule = read_json(run_dir / "schedule.json")
    if schedule != build_schedule(benchmark_config, timed_queries):
        raise AssertionError("stored schedule differs from deterministic reconstruction")
    blocks = schedule.get("blocks", [])
    expected_block_keys = {
        (round_number, method, threshold)
        for round_number in range(1, int(stage["rounds"]) + 1)
        for method in methods
        for threshold in filters
    }
    observed_block_keys = {
        (int(block["round"]), str(block["method"]), int(block["filter_threshold"]))
        for block in blocks
    }
    if (
        schedule.get("protocol_id") != protocol["protocol_id"]
        or schedule.get("stage_id") != stage["stage_id"]
        or int(schedule.get("scale_rows", -1)) != scale_rows
        or observed_block_keys != expected_block_keys
        or [int(block["block_index"]) for block in blocks]
        != list(range(1, len(blocks) + 1))
    ):
        raise AssertionError("schedule identity or method/filter/round matrix is invalid")
    expected_sequence: list[tuple[int, int, str, int, int, int]] = []
    for block in blocks:
        if not all(
            token in str(block["block_schedule_domain"])
            for token in (
                protocol["protocol_id"],
                stage["stage_id"],
                str(block["round"]),
                str(scale_rows),
            )
        ):
            raise AssertionError("block schedule hash domain omits required identity")
        orders = block["query_order_by_repetition"]
        if len(orders) != int(stage["repetitions"]):
            raise AssertionError("schedule repetition count is invalid")
        for repetition, order in enumerate(orders, start=1):
            if sorted(int(value) for value in order) != sorted(timed_queries):
                raise AssertionError("scheduled query order is not a timed-query permutation")
            expected_sequence.extend(
                (
                    int(block["block_index"]),
                    int(block["round"]),
                    str(block["method"]),
                    int(block["filter_threshold"]),
                    repetition,
                    int(query_id),
                )
                for query_id in order
            )
    observed_sequence = [
        (
            int(row["block_index"]),
            int(row["round"]),
            str(row["method"]),
            int(row["filter_threshold"]),
            int(row["repetition"]),
            int(row["query_id"]),
        )
        for row in executions
    ]
    if observed_sequence != expected_sequence or [int(row["sequence_index"]) for row in executions] != list(
        range(1, len(executions) + 1)
    ):
        raise AssertionError("execution order differs from the stored schedule")

    warmups = read_jsonl(run_dir / "warmups.jsonl")
    expected_warmups = (
        int(stage["rounds"])
        * len(methods)
        * len(filters)
        * int(stage["warmup_query_count"])
    )
    if len(warmups) != expected_warmups:
        raise AssertionError(f"expected {expected_warmups} warm-ups, found {len(warmups)}")
    expected_warmup_order = [
        (
            int(block["block_index"]),
            int(block["round"]),
            str(block["method"]),
            int(block["filter_threshold"]),
            int(query_id),
        )
        for block in blocks
        for query_id in warmup_queries[: int(stage["warmup_query_count"])]
    ]
    observed_warmup_order = [
        (
            int(row["block_index"]),
            int(row["round"]),
            str(row["method"]),
            int(row["filter_threshold"]),
            int(row["query_id"]),
        )
        for row in warmups
    ]
    if observed_warmup_order != expected_warmup_order:
        raise AssertionError("warm-up order/matrix differs from the stored schedule")
    for row in warmups:
        verify_result_fields(row, selected_buckets, int(row["filter_threshold"]), k)
        verify_source_distances(row, query_vectors[int(row["query_id"])], vectors, id_to_position)
        method, round_number = str(row["method"]), int(row["round"])
        if (
            row.get("run_id") != run_dir.name
            or row.get("scale_rows") != scale_rows
            or row.get("build_id") != f"{run_dir.name}-round-{round_number}-build-1"
            or row.get("backend_pid") != backend_pids[method]
            or row.get("returned_k") is not (int(row["returned_count"]) == k)
            or not 0 <= int(row["returned_count"]) <= k
        ):
            raise AssertionError("warm-up identity or completeness evidence is invalid")
        if not all(
            bool(row[name])
            for name in ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")
        ) or int(row["returned_count"]) + int(row["shortfall"]) != k:
            raise AssertionError("warm-up result evidence is invalid")

    plans = read_jsonl(run_dir / "plan_assertions.jsonl")
    plan_keys = {(str(row["method"]), int(row["filter_threshold"])) for row in plans}
    if (
        len(plans) != len(methods) * len(filters)
        or plan_keys != {(method, threshold) for method in methods for threshold in filters}
        or not all(bool(row["passed"]) for row in plans)
    ):
        raise AssertionError("plan audit matrix is incomplete or failed")
    plan_files = list((run_dir / "plans").glob("*.json"))
    if len(plan_files) != len(plans):
        raise AssertionError("raw plan count differs from plan assertions")
    for plan in plans:
        method, threshold = str(plan["method"]), int(plan["filter_threshold"])
        expected_plan_id = hashlib.sha256(f"m2-plan-v1|{scale_rows}|{method}|{threshold}|{timed_queries[0]}".encode()).hexdigest()[:20]
        if (
            plan.get("plan_id") != expected_plan_id
            or plan.get("raw_plan_path") != f"plans/{expected_plan_id}.json"
            or plan.get("scale_rows") != scale_rows
            or plan.get("query_id") != timed_queries[0]
            or plan.get("backend_pid") != backend_pids[method]
            or plan.get("observed_session_settings") != method_sessions["settings"][method]
        ):
            raise AssertionError("plan identity/session evidence differs from run")
        prepared_plan = plan.get("prepared_statement", {})
        if (
            plan.get("plan_capture") != "EXPLAIN ANALYZE EXECUTE of the workload prepared generic statement"
            or prepared_plan.get("statement") != search_sql(method, threshold, k).replace("%s", "$1")
            or prepared_plan.get("parameter_types") != "{vector}"
            or int(prepared_plan.get("generic_plans_before_explain", 0)) < 1
            or int(prepared_plan.get("generic_plans_after_explain", -1)) != int(prepared_plan.get("generic_plans_before_explain", 0)) + 1
            or prepared_plan.get("custom_plans_before_explain") != 0
            or prepared_plan.get("custom_plans_after_explain") != 0
        ):
            raise AssertionError("plan was not captured from the same prepared generic statement")
        raw_document = json.loads((run_dir / str(plan["raw_plan_path"])).read_text(encoding="utf-8"))
        recomputed = verify_plan_document(
            method=str(plan["method"]),
            threshold=int(plan["filter_threshold"]),
            document=raw_document,
            observed_settings={
                str(key): str(value)
                for key, value in plan["observed_session_settings"].items()
            },
            fetched_result_count=int(plan["fetched_result_count"]),
        )
        if not recomputed["passed"] or recomputed["failures"]:
            raise AssertionError(f"independent plan verification failed: {plan['plan_id']}")
        if any(plan.get(name) != value for name, value in recomputed.items()):
            raise AssertionError("stored plan assertions differ from the raw plan")
        if int(plan["actual_rows"]) != len(plan["fetched_result_ids"]):
            raise AssertionError("plan actual rows differ from preserved fetched IDs")
        ids, distances = plan["fetched_result_ids"], plan["fetched_result_distances"]
        if len(ids) != len(distances) or not all(math.isfinite(value) and value >= 0 for value in distances):
            raise AssertionError("plan fetched results contain invalid distances")
        result_validation = validate_returned_results(ids, distances, k=k, selected_buckets=selected_buckets, threshold=threshold)
        if not all(result_validation[name] for name in ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")):
            raise AssertionError("plan fetched rows fail result validation")
    plan_ids = {(row["method"], row["filter_threshold"]): row["plan_id"] for row in plans}
    if any(row.get("plan_audit_id") != plan_ids[(row["method"], row["filter_threshold"])] for row in executions):
        raise AssertionError("timed execution is linked to the wrong plan audit")

    prepared = read_json(run_dir / "prepared_statements.json")
    for method in methods:
        statements = prepared.get(method, [])
        if len(statements) != len(filters):
            raise AssertionError(f"prepared statement count differs for {method}")
        for statement in statements:
            if (
                statement.get("parameter_types") != "{vector}"
                or "$2" in str(statement.get("statement"))
                or int(statement.get("generic_plans", 0)) <= 0
                or int(statement.get("custom_plans", -1)) != 0
            ):
                raise AssertionError(f"prepared statement evidence is invalid for {method}")
        if {statement["statement"] for statement in statements} != {search_sql(method, threshold, k).replace("%s", "$1") for threshold in filters}:
            raise AssertionError(f"prepared SQL differs from the single-vector search contract for {method}")
    for plan in plans:
        audited = plan["prepared_statement"]
        final_statements = [row for row in prepared[plan["method"]] if row["name"] == audited["name"]]
        if len(final_statements) != 1 or final_statements[0]["statement"] != audited["statement"] or final_statements[0]["generic_plans"] < audited["generic_plans_after_explain"]:
            raise AssertionError("plan-audited prepared statement was replaced before timed execution")

    database = read_json(run_dir / "database_evidence.json")
    if (
        int(database.get("exact_count", -1)) != scale_rows
        or int(database.get("hnsw_count", -1)) != scale_rows
        or int(database.get("unequal_row_count", -1)) != 0
        or database.get("dimensions") != {"minimum": 128, "maximum": 128}
        or database.get("nonfinite_vector_counts", {}).get("exact") != 0
        or database.get("nonfinite_vector_counts", {}).get("hnsw") != 0
    ):
        raise AssertionError("physical table equivalence/dimension/finiteness evidence failed")
    source_digest = source_stream_checksum(expected_scale["selected_base_ids"], vectors, expected_scale["filter_buckets"])
    if (
        database.get("source_vector_stream_sha256") != source_digest
        or database.get("ordered_vector_stream_sha256") != source_digest
        or database.get("all_source_rows_equal") is not True
        or database.get("rank_contract") != {"distinct_ranks": scale_rows, "minimum": 0, "maximum": scale_rows - 1, "bucket_mismatches": 0}
        or database.get("filter_counts") != {str(threshold): {"exact": filter_counts[str(threshold)], "hnsw": filter_counts[str(threshold)], "expected": filter_counts[str(threshold)]} for threshold in filters}
    ):
        raise AssertionError("physical source/rank/filter evidence differs from deterministic SIFT scale")
    if json.loads((run_dir / "relation_sizes.json").read_text()) != database.get("relation_sizes"):
        raise AssertionError("relation size artifacts disagree")
    source_samples = read_json(run_dir / "source_vector_samples.json")
    sampled_positions = np.linspace(0, scale_rows - 1, min(100, scale_rows), dtype=int)
    if source_samples != {"sample_count": len(sampled_positions), "ids": sorted(int(expected_scale["selected_base_ids"][position]) for position in sampled_positions), "float32_exact_equality": True, "normalization_applied": False}:
        raise AssertionError("source-vector sample evidence differs from deterministic sample")
    indexes = database.get("indexes", [])
    if any(
        row.get("table") == "sift_exact" and "(embedding" in row.get("definition", "")
        for row in indexes
    ) or any(
        row.get("table") == "sift_hnsw" and "(filter_bucket)" in row.get("definition", "")
        for row in indexes
    ):
        raise AssertionError("physical exact/HNSW index separation is invalid")
    if len([row for row in indexes if row.get("table") == "sift_exact" and "USING btree (filter_bucket)" in row.get("definition", "")]) != 1 or len([row for row in indexes if row.get("index") == "sift_hnsw_embedding_idx" and "USING hnsw (embedding vector_l2_ops)" in row.get("definition", "") and "m='16'" in row["definition"] and "ef_construction='64'" in row["definition"]]) != 1:
        raise AssertionError("required exact metadata/HNSW index definitions are absent")

    cache = read_json(run_dir / "cache_reset.json")
    if (
        int(cache.get("after", {}).get("buffers_used", -1)) != 0
        or cache.get("operating_system_cache_flushed") is not False
    ):
        raise AssertionError("qualification shared-buffer reset evidence is invalid")

    stored_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    verify_summary(stored_summary, executions)
    phases = read_json(run_dir / "phase_metrics.json")
    for name in (
        "copy_exact_ns",
        "copy_hnsw_from_exact_ns",
        "hnsw_build_ns",
        "ground_truth_generation_ns",
        "ground_truth_determinism_reexecution_ns",
        "timed_workload_and_warmups_ns",
        "final_validation_ns",
        "total_before_final_artifacts_ns",
    ):
        if int(phases.get(name, 0)) <= 0:
            raise AssertionError(f"missing/non-positive phase duration {name}")
    resources = read_json(run_dir / "resource_observations.json")
    power_after = resources.get("energy_mode_after", {})
    if resources.get("energy_mode_at_start") != power or power_after.get("ac_power_detected") is not True or power_after.get("energy_settings_stdout") != power.get("energy_settings_stdout"):
        raise AssertionError("power/energy settings changed during execution")
    projection = resources.get("projection", {})
    if (
        projection.get("projection_kind")
        != "mechanical qualification planning estimate"
        or float(projection.get("estimated_full_pipeline_seconds", 0)) <= 0
        or int(projection.get("estimated_full_matrix_artifact_bytes", 0)) <= 0
        or int(projection.get("estimated_1m_relation_bytes_linear", 0)) <= 0
    ):
        raise AssertionError("full-pipeline resource projection is incomplete")

    validation = read_json(run_dir / "validation_report.json")
    if not validation.get("passed"):
        raise AssertionError("validation_report.json is not passing")
    expected_checks = {
        "physical_scale_rows": scale_rows, "exact_filter_counts": filter_counts,
        "ground_truth_records": len(ground_truth_rows), "ground_truth_deterministic_reexecutions": len(ground_truth_rows),
        "independent_ground_truth_checks": len(validation_keys), "plan_audits": len(plans),
        "plan_failures": 0, "warmups": len(warmups), "timed_executions": len(executions),
        "execution_errors": 0,
    }
    if validation.get("run_id") != run_dir.name or any(validation.get("checks", {}).get(name) != value for name, value in expected_checks.items()):
        raise AssertionError("validation-report counts or identities differ from independent verification")
    if complete.get("timed_executions") != len(executions) or complete.get("stage_id") != stage["stage_id"]:
        raise AssertionError("completion marker counts/stage differ from verified artifacts")
    # A verification is read-only: recheck every immutable payload after inspection.
    verify_checksum_manifest(run_dir)
    return {
        "run_id": run_dir.name,
        "stage_id": stage["stage_id"],
        "ground_truth_records": len(ground_truth_rows),
        "timed_executions": len(executions),
        "warmups": len(warmups),
        "plan_audits": len(plans),
        "checksums_valid": True,
        "independent_source_ground_truth_checks": len(validation_keys),
        "deterministic_query_and_schedule_verified": True,
        "artifact_checksums_unchanged_after_verification": True,
        "passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    result = verify_run(args.run_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
