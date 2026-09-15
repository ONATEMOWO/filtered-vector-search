#!/usr/bin/env python3
"""Verify the machine-readable smoke results and their recorded access paths."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "raw_results" / "smoke_results.csv"
HNSW_INDEX = "smoke_items_embedding_hnsw"


def main() -> None:
    with RESULTS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 250:
        raise AssertionError(f"expected 250 measured rows, found {len(rows)}")

    ground_truth: dict[tuple[int, int], list[int]] = {}
    for row in rows:
        ids = json.loads(row["result_ids"])
        if len(ids) != int(row["returned_count"]):
            raise AssertionError("returned_count does not match result_ids")
        if len(ids) != len(set(ids)):
            raise AssertionError("a top-k result contains duplicate IDs")
        if float(row["latency_ms"]) < 0:
            raise AssertionError("latency must be nonnegative")

        indexes = json.loads(row["plan_index_names"])
        if row["method"] == "exact":
            if HNSW_INDEX in indexes:
                raise AssertionError("exact-labeled row used HNSW")
            key = (int(row["query_id"]), int(row["filter_threshold"]))
            if key in ground_truth and ground_truth[key] != ids:
                raise AssertionError(f"exact result changed across repetitions for {key}")
            ground_truth[key] = ids
        elif row["method"] == "hnsw":
            if HNSW_INDEX not in indexes:
                raise AssertionError("HNSW-labeled row did not use the HNSW index")
        else:
            raise AssertionError(f"unknown method {row['method']}")

    if len(ground_truth) != 25:
        raise AssertionError(f"expected 25 exact query/filter groups, found {len(ground_truth)}")

    for row in rows:
        key = (int(row["query_id"]), int(row["filter_threshold"]))
        ids = json.loads(row["result_ids"])
        recomputed = len(set(ids).intersection(ground_truth[key])) / int(row["k"])
        if not math.isclose(recomputed, float(row["recall_at_k"])):
            raise AssertionError(f"Recall@k mismatch for {key}, method={row['method']}")

    expected_plans = {
        "exact_filter_50_query_1.json",
        "exact_filter_1_query_1.json",
        "hnsw_filter_50_query_1.json",
        "hnsw_filter_1_query_1.json",
    }
    actual_plans = {path.name for path in (RESULTS.parent / "explain").glob("*.json")}
    if not expected_plans.issubset(actual_plans):
        raise AssertionError(f"missing representative plans: {sorted(expected_plans - actual_plans)}")

    print("ok: 250 result rows, exact determinism, Recall@k, and all access paths verified")


if __name__ == "__main__":
    main()

