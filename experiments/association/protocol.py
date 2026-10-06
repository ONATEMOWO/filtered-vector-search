"""Frozen two-scale metadata contrast; historical profiles remain unchanged."""
from __future__ import annotations
import hashlib
from pathlib import Path
from experiments.milestone2.config import canonical_json_bytes, sha256_json
from experiments.preparation.protocol import configure_session, validate_server_settings

ROOT = Path(__file__).resolve().parents[2]
METHODS = ("exact", "hnsw_standard", "hnsw_iterative")
MODES = ("legacy", "radial")
FILTERS = (50, 20, 10, 5, 1)
K = 10
STAGES = ((100000, 1), (250000, 1), (250000, 2), (100000, 2))
PROTOCOL = {
    "schema_version": 1, "protocol_id": "metadata-association-v1",
    "stages": [list(s) for s in STAGES], "dimensions": 128, "k": K,
    "methods": list(METHODS), "metadata_modes": list(MODES),
    "filter_thresholds": list(FILTERS), "measured_query_count": 200,
    "warmup_query_count": 20, "repetitions": 5,
    "metadata_algorithm": "fixed-anchor-squared-l2-within-consecutive-100-rank-blocks-v1",
    "anchor_train_id": 0, "metadata_block_size": 100,
    "neighborhood_sizes": [40, 100, 1000], "primary_neighborhood_size": 100,
    "association_permutations": 99, "association_seed": 20261006,
    "association_gate_thresholds": [50, 5], "permutation_rng": "PCG64",
    "preparation": "20 disjoint warmups; no measured-query exposure",
    "reset": "checkpoint and verified shared-buffer eviction per metadata mode",
    "os_cache_flushed": False, "steady_state_claimed": False,
    "exact_work_mem": "4MB", "ann_work_mem": "64MB", "shared_buffers": "128MB",
    "hnsw_m": 16, "hnsw_ef_construction": 64, "hnsw_ef_search": 40,
    "iterative_scan": "strict_order", "max_scan_tuples": 20000,
    "scan_mem_multiplier": 1, "jit": "off", "plan_cache_mode": "force_generic_plan",
    "independent_truth_checks_per_mode": 20,
    "expected_measured_per_stage": 30000, "expected_warmups_per_stage": 600,
    "expected_plans_per_stage": 30, "expected_truth_per_stage": 2000,
    "resource_min_available_bytes": 2147483648,
    "resource_min_disk_bytes": 10737418240,
    "source_protocol": "config/milestone2/protocol.json",
    "max_scale_rows": 250000, "stop_after_stages": True,
}

def stage_config(scale: int, build: int) -> dict:
    if type(scale) is not int or type(build) is not int or (scale, build) not in STAGES:
        raise ValueError("only the four frozen 100k/250k stages are authorized")
    return {**PROTOCOL, "scale_rows": scale, "build_number": build}

def validate_config(config: dict) -> None:
    expected = stage_config(config.get("scale_rows"), config.get("build_number"))
    if canonical_json_bytes(config) != canonical_json_bytes(expected):
        raise ValueError("configuration differs from frozen association protocol")

def ordered(domain: str, values: list) -> list:
    return sorted(values, key=lambda v: (hashlib.sha256(f"{domain}|{v}".encode()).digest(), str(v)))

def schedule(config: dict, query_ids: list[int]) -> dict:
    validate_config(config)
    if (len(query_ids) != 200 or len(set(query_ids)) != 200
            or any(type(q) is not int or not 0 <= q < 10000 for q in query_ids)):
        raise ValueError("exactly 200 distinct measured queries required")
    build = config["build_number"]
    keys = ordered("association-block-v1", [f"{m}|{t}" for m in METHODS for t in FILTERS])
    if build == 2:
        keys.reverse()
    blocks = []
    for index, key in enumerate(keys, 1):
        method, threshold = key.split("|")
        blocks.append({"block_index": index, "method": method, "filter_threshold": int(threshold),
                       "query_order_by_repetition": [ordered(f"association-query-v1|{build}|{r}", query_ids)
                                                      for r in range(1, 6)]})
    return {"modes": list(MODES if build == 1 else reversed(MODES)), "blocks": blocks}

def config_digest(config: dict) -> str:
    validate_config(config)
    return sha256_json(config)
