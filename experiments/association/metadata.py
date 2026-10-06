"""Frozen, scale-inheriting radial metadata and independent local diagnostics.

All calculations are outside PostgreSQL query timing. A 100-row block is a
consecutive block of the existing content-blind global scale ordering; it is
not a vector cluster. Synthetic metadata is not a claim of semantic realism.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


BLOCK_SIZE = 100
DIMENSION = 128
FILTERS = (50, 20, 10, 5, 1)
NEIGHBORHOOD_SIZES = (40, 100, 1000)
PRIMARY_L = 100
GATE_THRESHOLDS = (50, 5)
ALGORITHM = "fixed-anchor-squared-l2-within-consecutive-100-rank-blocks-v1"


def _hash_array(values: np.ndarray, dtype: str) -> str:
    return hashlib.sha256(np.asarray(values, dtype=dtype).tobytes()).hexdigest()


def _ids(values: Any) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1 or not np.issubdtype(array.dtype, np.integer):
        raise ValueError("base_ids must be a one-dimensional integer array")
    if len(array) == 0 or len(array) % BLOCK_SIZE:
        raise ValueError("row count must be a positive multiple of 100")
    if np.any(array < 0) or np.any(array > np.iinfo(np.int64).max):
        raise ValueError("base_ids must be nonnegative signed-int64-compatible IDs")
    array = array.astype(np.int64, copy=False)
    if len(np.unique(array)) != len(array):
        raise ValueError("base_ids must be unique")
    return array


def _real_array(values: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.shape != shape or array.dtype.kind not in "fiu":
        raise ValueError(f"{name} must be a real numeric array with shape {shape}")
    array = array.astype(np.float64, copy=False)
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array


def _squared_l2(vectors: np.ndarray, query: np.ndarray) -> np.ndarray:
    # Direct differences avoid cancellation in norm(a)+norm(b)-2*dot(a,b).
    # Chunking bounds temporary memory independently of the physical scale.
    distances = np.empty(len(vectors), dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        for start in range(0, len(vectors), 16384):
            difference = vectors[start : start + 16384] - query
            distances[start : start + len(difference)] = np.einsum(
                "ij,ij->i", difference, difference, optimize=False
            )
    if not np.all(np.isfinite(distances)):
        raise ValueError("float64 squared L2 overflowed; finite scores are required")
    return distances


def _radial_labels(values: Any, count: int) -> np.ndarray:
    labels = np.asarray(values)
    if labels.shape != (count,) or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("radial labels must be a one-dimensional integer array")
    if not np.array_equal(
        np.sort(labels.reshape(-1, BLOCK_SIZE), axis=1),
        np.broadcast_to(np.arange(BLOCK_SIZE), (count // BLOCK_SIZE, BLOCK_SIZE)),
    ):
        raise ValueError("each consecutive block must contain radial labels 0..99 exactly once")
    return labels.astype(np.int16, copy=False)


def build_metadata(
    base_ids: np.ndarray, vectors: np.ndarray, anchor: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return radial labels in input scale-rank order and a JSON manifest.

    The caller must supply the frozen SIFT train[0] anchor. This general numeric
    function records its bytes but cannot authenticate its origin; the runner
    and independent verifier must check it against the source dataset.
    """
    ids = _ids(base_ids)
    matrix = _real_array(vectors, (len(ids), DIMENSION), "vectors")
    origin = _real_array(anchor, (DIMENSION,), "anchor")
    scores = _squared_l2(matrix, origin)
    order = np.lexsort(
        (ids.reshape(-1, BLOCK_SIZE), scores.reshape(-1, BLOCK_SIZE)), axis=1
    )
    labels = np.empty(order.shape, dtype=np.int16)
    np.put_along_axis(labels, order, np.arange(BLOCK_SIZE, dtype=np.int16)[None, :], axis=1)
    radial = labels.ravel()
    ordered_scores = np.take_along_axis(scores.reshape(-1, BLOCK_SIZE), order, axis=1)
    boundaries: dict[str, Any] = {}
    for threshold in FILTERS:
        last_in = ordered_scores[:, threshold - 1]
        first_out = ordered_scores[:, threshold]
        boundaries[str(threshold)] = {
            "last_included_squared_distance_min": float(np.min(last_in)),
            "last_included_squared_distance_median": float(np.median(last_in)),
            "last_included_squared_distance_max": float(np.max(last_in)),
            "first_excluded_squared_distance_min": float(np.min(first_out)),
            "first_excluded_squared_distance_median": float(np.median(first_out)),
            "first_excluded_squared_distance_max": float(np.max(first_out)),
            "boundary_tied_block_count": int(np.count_nonzero(last_in == first_out)),
            "all_block_boundary_pairs_sha256": _hash_array(np.column_stack((last_in, first_out)), "<f8"),
        }
    manifest = {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "row_count": len(ids),
        "dimension": DIMENSION,
        "block_size": BLOCK_SIZE,
        "block_count": len(ids) // BLOCK_SIZE,
        "block_definition": "consecutive blocks in existing global SHA256 scale-rank order",
        "score": "sum of float64 squared coordinate differences from fixed SIFT train[0]",
        "tie_break": "ascending base_id within each 100-row block",
        "label": "zero-based rank 0..99 within each block",
        "legacy_label": "zero-based scale_rank modulo 100; unchanged",
        "anchor_source_base_id": 0,
        "anchor_float64_le_sha256": _hash_array(origin, "<f8"),
        "anchor_vector": origin.tolist(),
        "ordered_base_ids_int64_le_sha256": _hash_array(ids, "<i8"),
        "radial_labels_int16_le_sha256": _hash_array(radial, "<i2"),
        "scores_float64_le_sha256": _hash_array(scores, "<f8"),
        "filter_counts": {str(t): int(np.count_nonzero(radial < t)) for t in FILTERS},
        "squared_score_min": float(scores.min()),
        "squared_score_max": float(scores.max()),
        "score_boundary_summary_by_filter": boundaries,
        "scale_inheritance": "labels are unchanged for every prefix ending at a 100-row block boundary",
        "limitation": "block-specific radial boundaries; construction alone does not prove local association",
    }
    if len(ids) >= 100000:
        manifest["prefix_100k_ordered_base_ids_int64_le_sha256"] = _hash_array(ids[:100000], "<i8")
        manifest["prefix_100k_radial_labels_int16_le_sha256"] = _hash_array(radial[:100000], "<i2")
    return radial, manifest


def _local_counts(positions: np.ndarray, labels: np.ndarray) -> dict[str, dict[str, int]]:
    local_labels = labels[positions]
    return {
        str(threshold): {
            str(size): int(np.count_nonzero(local_labels[:size] < threshold))
            for size in NEIGHBORHOOD_SIZES
        }
        for threshold in FILTERS
    }


def neighborhoods(
    base_ids: np.ndarray,
    vectors: np.ndarray,
    query_vectors: Mapping[int, np.ndarray],
    legacy: np.ndarray,
    radial: np.ndarray,
    *,
    anchor: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Compute exact unfiltered top1000; arbitrary equal-distance ties use ID.

    A mapping preserves the real SIFT query IDs. The output is query-ID sorted,
    independent of mapping insertion order. There must be at least 1000 rows.
    """
    ids = _ids(base_ids)
    if len(ids) < max(NEIGHBORHOOD_SIZES):
        raise ValueError("exact neighborhoods require at least 1000 source rows")
    matrix = _real_array(vectors, (len(ids), DIMENSION), "vectors")
    baseline = np.asarray(legacy)
    if baseline.dtype.kind not in "iu" or not np.array_equal(baseline, np.arange(len(ids)) % 100):
        raise ValueError("legacy metadata must equal scale_rank modulo 100")
    radial = _radial_labels(radial, len(ids))
    if not isinstance(query_vectors, Mapping) or not query_vectors:
        raise ValueError("query_vectors must be a nonempty mapping from query IDs to vectors")
    if any(isinstance(key, (bool, np.bool_)) or not isinstance(key, (int, np.integer)) or key < 0 for key in query_vectors):
        raise ValueError("query IDs must be nonnegative integers")
    origin = None if anchor is None else _real_array(anchor, (DIMENSION,), "anchor")
    records = []
    for query_id in sorted(query_vectors):
        query = _real_array(query_vectors[query_id], (DIMENSION,), "query vector")
        distances = _squared_l2(matrix, query)
        boundary = np.partition(distances, 999)[999]
        candidates = np.flatnonzero(distances <= boundary)
        positions = candidates[np.lexsort((ids[candidates], distances[candidates]))[:1000]]
        record = {
            "query_id": int(query_id),
            "neighbor_ids": ids[positions].tolist(),
            "squared_distances": distances[positions].tolist(),
            "distance_computation": "direct float64 squared L2; ascending distance then base_id",
            "neighborhood_sizes": list(NEIGHBORHOOD_SIZES),
            "local_counts": {
                "legacy": _local_counts(positions, baseline),
                "radial": _local_counts(positions, radial),
            },
        }
        if origin is not None:
            distance_squared = float(_squared_l2(query[None, :], origin)[0])
            record["query_anchor_squared_distance"] = distance_squared
            record["query_anchor_distance"] = float(np.sqrt(distance_squared))
        records.append(record)
    return records


def _density_summary(counts: np.ndarray, size: int, threshold: int) -> dict[str, Any]:
    if len(counts) == 0:
        return {"query_count": 0}
    fractions = counts.astype(np.float64) / size
    selectivity = threshold / 100
    mean = float(np.mean(fractions))
    variance = float(np.var(fractions, ddof=0))
    return {
        "query_count": len(counts),
        "global_selectivity": selectivity,
        "mean_local_fraction": mean,
        "variance_local_fraction": variance,
        "std_local_fraction": float(np.sqrt(variance)),
        "squared_mean_displacement": (mean - selectivity) ** 2,
        "D_mean_squared_deviation_from_global": float(np.mean((fractions - selectivity) ** 2)),
        "local_fraction_quantiles_linear": {
            str(q): float(np.quantile(fractions, q, method="linear"))
            for q in (0, 0.05, 0.25, 0.5, 0.75, 0.95, 1)
        },
        "mean_enrichment": mean / selectivity,
        "zero_local_fraction_rate": float(np.mean(counts == 0)),
        "counts": counts.tolist(),
    }


def _permuted_labels(count: int, rng: np.random.Generator) -> np.ndarray:
    """Independently permute the fixed balanced multiset inside each block."""
    baseline = np.broadcast_to(np.arange(100, dtype=np.int16), (count // 100, 100))
    return rng.permuted(baseline, axis=1).ravel()


def association_diagnostics(
    records: Sequence[dict[str, Any]],
    base_ids: np.ndarray,
    radial: np.ndarray,
    measured_ids: Sequence[int],
    seed: int = 20261006,
    permutations: int = 99,
) -> dict[str, Any]:
    """Check the fixed manipulation gate without looking at ANN outcomes.

    Neighbor IDs are mapped back to source rows and every stored local count is
    recomputed. The independent verifier must additionally recompute distances
    and neighbor selection from source vectors. Other records are summarized as
    the disjoint warmup set, never included in the manipulation gate.
    """
    ids = _ids(base_ids)
    radial = _radial_labels(radial, len(ids))
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if isinstance(permutations, (bool, np.bool_)) or not isinstance(permutations, (int, np.integer)) or permutations < 1:
        raise ValueError("permutations must be a positive integer")
    measured = list(measured_ids)
    if not measured or any(isinstance(q, (bool, np.bool_)) or not isinstance(q, (int, np.integer)) or q < 0 for q in measured):
        raise ValueError("measured IDs must be nonnegative integers and nonempty")
    if len(set(measured)) != len(measured):
        raise ValueError("measured IDs must be unique")
    measured = sorted(int(q) for q in measured)
    by_query: dict[int, dict[str, Any]] = {}
    positions_by_query: dict[int, np.ndarray] = {}
    id_order = np.argsort(ids)
    sorted_ids = ids[id_order]
    baseline = np.arange(len(ids)) % 100
    for record in records:
        query_id = record.get("query_id")
        if isinstance(query_id, bool) or not isinstance(query_id, int) or query_id < 0 or query_id in by_query:
            raise ValueError("neighborhood query IDs must be unique nonnegative integers")
        neighbors = np.asarray(record.get("neighbor_ids"))
        distances = np.asarray(record.get("squared_distances"))
        if neighbors.shape != (1000,) or neighbors.dtype.kind not in "iu" or len(np.unique(neighbors)) != 1000:
            raise ValueError("each neighborhood must contain 1000 unique integer IDs")
        if distances.shape != (1000,) or distances.dtype.kind not in "fiu" or not np.all(np.isfinite(distances)) or np.any(distances < 0):
            raise ValueError("each neighborhood must contain 1000 finite nonnegative distances")
        if not np.array_equal(np.lexsort((neighbors, distances)), np.arange(1000)):
            raise ValueError("neighborhood ordering must be canonical distance/ID order")
        locations = np.searchsorted(sorted_ids, neighbors)
        if np.any(locations >= len(ids)) or not np.array_equal(sorted_ids[np.minimum(locations, len(ids) - 1)], neighbors):
            raise ValueError("neighborhood contains an unknown base ID")
        positions = id_order[locations]
        expected = {"legacy": _local_counts(positions, baseline), "radial": _local_counts(positions, radial)}
        if record.get("local_counts") != expected:
            raise ValueError("stored local counts disagree with source labels and neighbor IDs")
        if any(
            type(record["local_counts"][mode][str(threshold)][str(size)]) is not int
            for mode in ("legacy", "radial")
            for threshold in FILTERS
            for size in NEIGHBORHOOD_SIZES
        ):
            raise ValueError("stored local counts must be JSON integers, not booleans or floats")
        by_query[query_id] = record
        positions_by_query[query_id] = positions
    if not set(measured).issubset(by_query):
        raise ValueError("a measured query lacks an exact neighborhood")
    warmups = sorted(set(by_query) - set(measured))
    groups: dict[str, Any] = {}
    for group_name, query_ids in (("measured", measured), ("warmup", warmups)):
        summaries = {
            mode: {
                str(threshold): {
                    str(size): _density_summary(
                        np.asarray([by_query[q]["local_counts"][mode][str(threshold)][str(size)] for q in query_ids]),
                        size,
                        threshold,
                    )
                    for size in NEIGHBORHOOD_SIZES
                }
                for threshold in FILTERS
            }
            for mode in ("legacy", "radial")
        }
        groups[group_name] = {"query_ids": query_ids, "summary": summaries}

    primary_positions = np.stack([positions_by_query[q][:PRIMARY_L] for q in measured])
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    null_D = {str(threshold): [] for threshold in FILTERS}
    permutation_hash = hashlib.sha256()
    for _ in range(int(permutations)):
        labels = _permuted_labels(len(ids), rng)
        permutation_hash.update(labels.astype("<i2", copy=False).tobytes())
        local = labels[primary_positions]
        for threshold in FILTERS:
            fractions = np.mean(local < threshold, axis=1)
            null_D[str(threshold)].append(float(np.mean((fractions - threshold / 100) ** 2)))
    primary: dict[str, Any] = {}
    for threshold in FILTERS:
        threshold_key = str(threshold)
        baseline_D = groups["measured"]["summary"]["legacy"][threshold_key][str(PRIMARY_L)]["D_mean_squared_deviation_from_global"]
        radial_D = groups["measured"]["summary"]["radial"][threshold_key][str(PRIMARY_L)]["D_mean_squared_deviation_from_global"]
        null_95 = float(np.quantile(null_D[threshold_key], 0.95, method="linear"))
        primary[threshold_key] = {
            "legacy_D": baseline_D,
            "radial_D": radial_D,
            "permutation_D": null_D[threshold_key],
            "permutation_D_p95_linear": null_95,
            "radial_exceeds_legacy": bool(radial_D > baseline_D),
            "radial_exceeds_permutation_p95": bool(radial_D > null_95),
            "passes": bool(radial_D > baseline_D and radial_D > null_95),
        }
    return {
        "schema_version": 1,
        "primary_neighborhood_size": PRIMARY_L,
        "primary_statistic": "mean across measured queries of (local qualifying fraction - global selectivity)^2",
        "gate_thresholds": list(GATE_THRESHOLDS),
        "gate_passed": all(primary[str(t)]["passes"] for t in GATE_THRESHOLDS),
        "gate_interpretation": "prespecified engineering manipulation check; not a population significance test or ANN outcome gate",
        "primary_by_filter": primary,
        "groups": groups,
        "permutation_null": {
            "replicates": int(permutations),
            "seed": int(seed),
            "rng": "numpy.random.Generator(PCG64)",
            "numpy_version": np.__version__,
            "algorithm": "Generator.permuted of labels 0..99 independently within every consecutive 100-row scale-rank block",
            "overlapping_neighborhood_membership_preserved": True,
            "replicate_labels_concatenated_int16_le_sha256": permutation_hash.hexdigest(),
            "quantile_method": "linear",
        },
    }
