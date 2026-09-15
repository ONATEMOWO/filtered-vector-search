"""Recall and returned-result validation for Milestone 2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def _unique_prefix(values: Iterable[int], k: int) -> list[int]:
    if k <= 0:
        raise ValueError("k must be positive")
    result = [int(value) for value in values][:k]
    if len(result) != len(set(result)):
        raise ValueError("result IDs must be unique")
    return result


def canonical_recall_at_k(
    approximate_ids: Iterable[int], canonical_exact_ids: Iterable[int], k: int
) -> float:
    """Set recall with a fixed denominator k, so missing rows reduce recall."""
    approximate = _unique_prefix(approximate_ids, k)
    canonical = _unique_prefix(canonical_exact_ids, k)
    if len(canonical) != k:
        raise ValueError(f"canonical ground truth must contain exactly {k} IDs")
    return len(set(approximate).intersection(canonical)) / k


def tie_aware_recall_at_k(
    approximate_ids: Iterable[int],
    strictly_closer_ids: Iterable[int],
    boundary_tie_ids: Iterable[int],
    k: int,
) -> float:
    """Credit required closer neighbors plus interchangeable kth-boundary ties."""
    approximate = set(_unique_prefix(approximate_ids, k))
    closer = set(int(value) for value in strictly_closer_ids)
    ties = set(int(value) for value in boundary_tie_ids)
    if closer.intersection(ties):
        raise ValueError("strictly closer and boundary-tie sets must be disjoint")
    if len(closer) >= k:
        raise ValueError("strictly closer set must contain fewer than k IDs")
    credit = len(approximate.intersection(closer))
    credit += min(k - len(closer), len(approximate.intersection(ties)))
    return credit / k


def validate_returned_results(
    ids: Sequence[int],
    distances: Sequence[float],
    *,
    k: int,
    selected_buckets: Mapping[int, int],
    threshold: int,
) -> dict[str, Any]:
    if len(ids) != len(distances):
        raise ValueError("result IDs and distances have different lengths")
    if len(ids) > k:
        raise ValueError("search returned more than k rows")
    ids_unique = len(ids) == len(set(int(value) for value in ids))
    scale_valid = all(int(value) in selected_buckets for value in ids)
    filter_valid = scale_valid and all(
        selected_buckets[int(value)] < threshold for value in ids
    )
    distance_order_valid = all(
        float(distances[index]) <= float(distances[index + 1]) + 1e-12
        for index in range(len(distances) - 1)
    )
    return {
        "returned_count": len(ids),
        "returned_k": len(ids) == k,
        "shortfall": k - len(ids),
        "ids_unique": ids_unique,
        "scale_valid": scale_valid,
        "filter_valid": filter_valid,
        "distance_order_valid": distance_order_valid,
    }
