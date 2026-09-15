#!/usr/bin/env python3
"""Independently verify a completed Milestone 2 qualification run directory."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiments.milestone2.artifacts import verify_checksum_manifest  # noqa: E402
from experiments.milestone2.ground_truth import ground_truth_index  # noqa: E402
from experiments.milestone2.metrics import (  # noqa: E402
    canonical_recall_at_k,
    tie_aware_recall_at_k,
)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def verify_run(run_dir: Path) -> dict[str, object]:
    required = {
        "config.json",
        "run_manifest.json",
        "dataset_manifest.json",
        "environment.json",
        "postgres_settings.json",
        "queries.json",
        "scale_manifest.json",
        "filter_counts.json",
        "ground_truth.jsonl",
        "executions.jsonl",
        "warmups.jsonl",
        "plan_assertions.jsonl",
        "database_evidence.json",
        "relation_sizes.json",
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
    verify_checksum_manifest(run_dir)

    resolved = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    protocol = resolved["protocol"]
    stage = resolved["stage"]
    filters = [int(value) for value in protocol["filter_thresholds"]]
    methods = [str(value) for value in protocol["methods"]]
    k = int(protocol["k"])
    query_manifest = json.loads((run_dir / "queries.json").read_text(encoding="utf-8"))
    timed_queries = [int(value) for value in query_manifest["qualification_timed_query_ids"]]

    ground_truth_rows = read_jsonl(run_dir / "ground_truth.jsonl")
    ground_truth = ground_truth_index(ground_truth_rows)
    expected_ground_truth = int(stage["ground_truth_query_count"]) * len(filters)
    if len(ground_truth) != expected_ground_truth:
        raise AssertionError("ground-truth matrix is incomplete")

    executions = read_jsonl(run_dir / "executions.jsonl")
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
        (method, threshold, query_id, repetition)
        for method in methods
        for threshold in filters
        for query_id in timed_queries
        for repetition in range(1, int(stage["repetitions"]) + 1)
    }
    observed_keys: set[tuple[str, int, int, int]] = set()
    for row in executions:
        key = (
            str(row["method"]),
            int(row["filter_threshold"]),
            int(row["query_id"]),
            int(row["repetition"]),
        )
        if key in observed_keys:
            raise AssertionError(f"duplicate execution key {key}")
        observed_keys.add(key)
        if row["error_type"] is not None or int(row["duration_ns"]) < 0:
            raise AssertionError(f"failed/invalid timed execution {key}")
        if not all(
            bool(row[name])
            for name in ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")
        ):
            raise AssertionError(f"result validation failure {key}")
        truth = ground_truth[(key[2], key[1])]
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
        if key[0] == "exact" and (
            canonical != 1.0 or tied != 1.0 or not bool(row["returned_k"])
        ):
            raise AssertionError(f"exact result is not complete ground truth {key}")
    if observed_keys != expected_keys:
        raise AssertionError("execution key matrix differs from configuration")

    warmups = read_jsonl(run_dir / "warmups.jsonl")
    expected_warmups = len(methods) * len(filters) * int(stage["warmup_query_count"])
    if len(warmups) != expected_warmups:
        raise AssertionError(f"expected {expected_warmups} warm-ups, found {len(warmups)}")
    plans = read_jsonl(run_dir / "plan_assertions.jsonl")
    if len(plans) != len(methods) * len(filters) or not all(bool(row["passed"]) for row in plans):
        raise AssertionError("plan audit matrix is incomplete or failed")
    plan_files = list((run_dir / "plans").glob("*.json"))
    if len(plan_files) != len(plans):
        raise AssertionError("raw plan count differs from plan assertions")

    validation = json.loads((run_dir / "validation_report.json").read_text(encoding="utf-8"))
    if not validation.get("passed"):
        raise AssertionError("validation_report.json is not passing")
    return {
        "run_id": run_dir.name,
        "stage_id": stage["stage_id"],
        "ground_truth_records": len(ground_truth_rows),
        "timed_executions": len(executions),
        "warmups": len(warmups),
        "plan_audits": len(plans),
        "checksums_valid": True,
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
