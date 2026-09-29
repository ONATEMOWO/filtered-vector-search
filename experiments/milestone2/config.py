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
        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError(f"duplicate JSON key {key!r} in {path}")
                value[key] = item
            return value

        value = json.load(handle, object_pairs_hook=reject_duplicate_keys)
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
    def is_full_benchmark(self) -> bool:
        return bool(self.stage["full_benchmark_authorized"])

    @property
    def round_numbers(self) -> tuple[int, ...]:
        # Each invocation physically loads and builds exactly one graph.
        return (int(self.stage.get("experiment_round", 1)),)

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
        ("scale_assignment", "base_count"): 1000000,
        ("scale_assignment", "ordered_ids_serialization"): "little-endian int32",
        (
            "scale_assignment",
            "expected_ordered_ids_sha256",
        ): "5fff299d2950d88779871ffa4b21660c51d295c44f09ffbee82bac7f164b1fc9",
        ("scale_assignment", "cache_format"): "NumPy .npy int32",
        (
            "scale_assignment",
            "expected_cache_sha256",
        ): "73913a6dc24c281c58e222bcd1f277fdd45ff48faa37bf511bad1a842490184e",
        ("hnsw", "m"): 16,
        ("hnsw", "ef_construction"): 64,
        ("hnsw", "ef_search"): 40,
        ("hnsw", "build_maintenance_work_mem"): "1GB",
        ("hnsw", "build_max_parallel_maintenance_workers"): 0,
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

    expected_dataset_contract = {
        "keys": {
            "base": "train",
            "queries": "test",
            "neighbors": "neighbors",
            "distances": "distances",
        },
        "expected_shapes": {
            "base": [1000000, 128],
            "queries": [10000, 128],
            "neighbors": [10000, 100],
            "distances": [10000, 100],
        },
        "expected_dtypes": {
            "base": "float32",
            "queries": "float32",
            "neighbors": "int32",
            "distances": "float32",
        },
        "expected_attributes": {"distance": "euclidean"},
        "preserve_values": True,
        "normalize_vectors": False,
        "id_origin": 0,
    }
    for key, expected_value in expected_dataset_contract.items():
        actual = protocol.get("dataset", {}).get(key)
        if actual != expected_value:
            raise ValueError(
                f"protocol dataset.{key} must be {expected_value!r}, got {actual!r}"
            )

    if stage.get("protocol_id") != protocol.get("protocol_id"):
        raise ValueError("stage protocol_id does not match the frozen protocol")
    accepted_stage_profiles = {
        "preflight-10k": {
            "schema_version": 1,
            "scale_rows": 10_000,
            "rounds": 1,
            "rebuild_hnsw_each_round": True,
            "ground_truth_query_count": 200,
            "timed_query_count": 5,
            "warmup_query_count": 20,
            "repetitions": 1,
            "independent_validation_count": 20,
            "record_resource_projection": True,
            "stop_after_stage": True,
            "full_benchmark_authorized": False,
        },
        "qualification-100k": {
            "schema_version": 1,
            "scale_rows": 100_000,
            "rounds": 1,
            "rebuild_hnsw_each_round": True,
            "ground_truth_query_count": 200,
            "timed_query_count": 20,
            "warmup_query_count": 20,
            "repetitions": 2,
            "independent_validation_count": 20,
            "record_resource_projection": True,
            "stop_after_stage": True,
            "full_benchmark_authorized": False,
        },
    }
    for round_number in (1, 2):
        accepted_stage_profiles[f"benchmark-100k-round-{round_number}"] = {
            **accepted_stage_profiles["qualification-100k"],
            "timed_query_count": 200,
            "repetitions": 5,
            "full_benchmark_authorized": True,
            "experiment_round": round_number,
            "campaign_id": "standalone-100k-v1",
            "cache_reset_method": "postgresql_restart_required",
            "larger_scales_authorized": False,
        }
    stage_id = str(stage["stage_id"])
    if stage_id not in accepted_stage_profiles:
        raise ValueError("only qualification or the two authorized standalone 100k stages may run")
    is_full = stage_id.startswith("benchmark-100k-round-")
    if not is_full and "experiment_round" in stage:
        raise ValueError("qualification round identity cannot be overridden")
    for key, expected_value in accepted_stage_profiles[stage_id].items():
        if stage.get(key) != expected_value:
            raise ValueError(
                f"stage {stage_id}.{key} must be {expected_value!r}, "
                f"got {stage.get(key)!r}"
            )
    scale_rows = int(stage.get("scale_rows", 0))
    if scale_rows not in ALLOWED_QUALIFICATION_SCALES:
        raise ValueError("qualification runner refuses scales above 100,000 rows")
    if int(stage.get("ground_truth_query_count", 0)) != 200:
        raise ValueError("qualification must generate all 200 selected-query ground truths")
    if int(stage.get("warmup_query_count", 0)) != 20:
        raise ValueError("the accepted warm-up set contains exactly 20 queries")
    if scale_rows != accepted_stage_profiles[stage_id]["scale_rows"]:
        raise ValueError("stage_id and physical scale_rows do not match")
    if int(stage.get("timed_query_count", 0)) <= 0:
        raise ValueError("timed_query_count must be positive")
    if not is_full and int(stage.get("timed_query_count", 0)) > 20:
        raise ValueError("bounded qualification may time at most 20 queries")
    if int(stage.get("repetitions", 0)) <= 0:
        raise ValueError("repetitions must be positive")
    if (not is_full and int(stage.get("repetitions", 0)) > 2) or int(stage.get("rounds", 0)) != 1:
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
