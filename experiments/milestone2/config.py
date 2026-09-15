"""Load and validate the frozen Milestone 2 protocol and bounded stage profiles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "config" / "milestone2" / "protocol.json"
ALLOWED_QUALIFICATION_SCALES = {10_000, 100_000}


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


@dataclass(frozen=True)
class BenchmarkConfig:
    protocol: dict[str, Any]
    stage: dict[str, Any]
    combined: dict[str, Any]
    config_sha256: str
    source_path: Path

    @property
    def scale_rows(self) -> int:
        return int(self.stage["scale_rows"])

    @property
    def filters(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.protocol["filter_thresholds"])

    @property
    def methods(self) -> tuple[str, ...]:
        return tuple(str(value) for value in self.protocol["methods"])

    @property
    def k(self) -> int:
        return int(self.protocol["k"])

    @property
    def measured_query_count(self) -> int:
        return int(self.stage["timed_query_count"])

    @property
    def ground_truth_query_count(self) -> int:
        return int(self.stage["ground_truth_query_count"])

    @property
    def warmup_query_count(self) -> int:
        return int(self.stage["warmup_query_count"])

    @property
    def repetitions(self) -> int:
        return int(self.stage["repetitions"])

    @property
    def rounds(self) -> int:
        return int(self.stage["rounds"])

    @property
    def expected_execution_count(self) -> int:
        return (
            len(self.methods)
            * len(self.filters)
            * self.measured_query_count
            * self.repetitions
            * self.rounds
        )


def load_config(stage_path: str | Path) -> BenchmarkConfig:
    source_path = Path(stage_path).resolve()
    protocol = read_json(PROTOCOL_PATH)
    stage = read_json(source_path)
    combined = {"protocol": protocol, "stage": stage}
    validate_config(protocol, stage)
    return BenchmarkConfig(
        protocol=protocol,
        stage=stage,
        combined=combined,
        config_sha256=sha256_json(combined),
        source_path=source_path,
    )


def validate_config(protocol: dict[str, Any], stage: dict[str, Any]) -> None:
    expected = {
        "postgresql_version": "17.11",
        "pgvector_version": "0.8.6",
        "dimensions": 128,
        "distance": "l2",
        "k": 10,
        "filter_thresholds": [50, 20, 10, 5, 1],
        "methods": ["exact", "hnsw_standard", "hnsw_iterative"],
        "final_scales": [100000, 250000, 500000, 1000000],
    }
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError(f"protocol {key!r} must be {value!r}")

    nested_expected = {
        ("dataset", "source_url"): "https://ann-benchmarks.com/sift-128-euclidean.hdf5",
        ("dataset", "expected_bytes"): 525128288,
        (
            "dataset",
            "expected_sha256",
        ): "dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984",
        ("hnsw", "m"): 16,
        ("hnsw", "ef_construction"): 64,
        ("hnsw", "ef_search"): 40,
        ("hnsw", "work_mem"): "64MB",
        ("hnsw", "standard_iterative_scan"): "off",
        ("hnsw", "iterative_scan"): "strict_order",
        ("hnsw", "max_scan_tuples"): 20000,
        ("hnsw", "scan_mem_multiplier"): 1,
        ("session", "jit"): "off",
        ("session", "statement_timeout"): "120s",
        ("session", "plan_cache_mode"): "force_generic_plan",
        ("session", "exact_scan_path_overrides"): False,
        ("final_execution", "rounds"): 2,
        ("final_execution", "repetitions"): 5,
        ("final_execution", "planned_timed_executions"): 120000,
        ("final_execution", "authorized"): False,
        ("cache_policy", "qualification_reset_method"): "pg_buffercache_evict_after_checkpoint",
        ("cache_policy", "final_benchmark_reset_method"): "postgresql_restart_required",
    }
    for (section, key), expected_value in nested_expected.items():
        actual = protocol.get(section, {}).get(key)
        if actual != expected_value:
            raise ValueError(
                f"protocol {section}.{key} must be {expected_value!r}, got {actual!r}"
            )

    if stage.get("protocol_id") != protocol.get("protocol_id"):
        raise ValueError("stage protocol_id does not match the frozen protocol")
    if stage.get("stage_id") not in {"preflight-10k", "qualification-100k"}:
        raise ValueError("only the accepted qualification stages may run")
    scale_rows = int(stage.get("scale_rows", 0))
    if scale_rows not in ALLOWED_QUALIFICATION_SCALES:
        raise ValueError("qualification runner refuses scales above 100,000 rows")
    if bool(stage.get("full_benchmark_authorized", False)):
        raise ValueError("full benchmark authorization must remain false in this milestone")
    if int(stage.get("ground_truth_query_count", 0)) != 200:
        raise ValueError("qualification must generate all 200 selected-query ground truths")
    if int(stage.get("warmup_query_count", 0)) != 20:
        raise ValueError("the accepted warm-up set contains exactly 20 queries")
    expected_stage_scales = {"preflight-10k": 10_000, "qualification-100k": 100_000}
    if scale_rows != expected_stage_scales[str(stage["stage_id"])]:
        raise ValueError("stage_id and physical scale_rows do not match")
    if int(stage.get("timed_query_count", 0)) <= 0:
        raise ValueError("timed_query_count must be positive")
    if int(stage.get("timed_query_count", 0)) > 20:
        raise ValueError("bounded qualification may time at most 20 queries")
    if int(stage.get("repetitions", 0)) <= 0:
        raise ValueError("repetitions must be positive")
    if int(stage.get("repetitions", 0)) > 2 or int(stage.get("rounds", 0)) != 1:
        raise ValueError("qualification profiles may not launch full repetitions or rounds")
    if int(stage.get("independent_validation_count", 0)) < 20:
        raise ValueError("at least 20 ground-truth combinations require independent validation")
    expected_filter_counts = {
        str(threshold): scale_rows * threshold // 100 for threshold in expected["filter_thresholds"]
    }
    if stage.get("expected_filter_counts") != expected_filter_counts:
        raise ValueError("stage expected_filter_counts do not match scale and protocol")
    expected_ground_truth = 200 * len(expected["filter_thresholds"])
    if int(stage.get("expected_ground_truth_combinations", 0)) != expected_ground_truth:
        raise ValueError("stage ground-truth combination count is inconsistent")
    expected_executions = (
        len(expected["methods"])
        * len(expected["filter_thresholds"])
        * int(stage["timed_query_count"])
        * int(stage["repetitions"])
        * int(stage["rounds"])
    )
    if int(stage.get("expected_timed_executions", 0)) != expected_executions:
        raise ValueError("stage timed execution count is inconsistent")
