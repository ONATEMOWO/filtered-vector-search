"""Fixed, bounded preparation-policy experiment; legacy profiles are untouched."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.milestone2.config import canonical_json_bytes, sha256_json
from experiments.milestone2.database import configure_method_connection, session_settings

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "config" / "preparation-policy-v1.json"
METHODS = ("exact", "hnsw_standard", "hnsw_iterative")
FILTERS = (50, 20, 10, 5, 1)
SCALE_ROWS = 100000
K = 10
PROTOCOL = {
    "schema_version": 1,
    "protocol_id": "preparation-policy-100k-v1",
    "purpose": "matched operational preparation-policy qualification, not cache-cause identification",
    "scale_rows": SCALE_ROWS,
    "build_numbers": [1, 2],
    "arms_by_build": {"1": ["A", "B"], "2": ["B", "A"]},
    "methods": list(METHODS),
    "filter_thresholds": list(FILTERS),
    "k": K,
    "measured_query_count": 200,
    "disjoint_warmup_query_count": 20,
    "measured_exposure_passes": {"A": 0, "B": 1},
    "repetitions": 5,
    "ground_truth_queries_per_build": 200,
    "independent_ground_truth_checks_per_build": 20,
    "expected_measured_executions": 60000,
    "expected_preparation_executions": 7200,
    "expected_plan_audits": 60,
    "reset_policy": "checkpoint_and_verified_shared_buffer_eviction_before_each_arm",
    "os_cache_flushed": False,
    "server_restart_required": False,
    "plan_probe": "first_disjoint_warmup_query",
    "block_order": "sha256-prep-block-v1-reversed-in-build2",
    "query_order": "sha256-prep-query-v1-shared-across-method-filter-arm",
    "source_protocol": "config/milestone2/protocol.json",
    "exact_work_mem": "4MB",
    "ann_work_mem": "64MB",
    "shared_buffers": "128MB",
    "engineering_drift_band": [0.8, 1.2],
    "drift_band_interpretation": "predeclared diagnostic tolerance, not proof of steady state",
    "hypothesis_support": "B lowers both median absolute log2 first/later query ratio and later-pass median range in both builds, evaluated separately for each method/filter",
    "max_scale_rows": 100000,
    "stop_after_campaign": True,
}

SESSION_CONTROLS = {
    "max_parallel_workers_per_gather": "2",
    "max_parallel_workers": "8",
    "effective_cache_size": "4GB",
    "random_page_cost": "4",
    "seq_page_cost": "1",
    "cpu_tuple_cost": "0.01",
    "cpu_index_tuple_cost": "0.005",
    "cpu_operator_cost": "0.0025",
    "effective_io_concurrency": "0",
}
SERVER_CONTROLS = {"shared_buffers": "128MB", "max_worker_processes": "8", "block_size": "8192"}


def load_protocol(path: Path = PROTOCOL_PATH) -> dict:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    # Canonical bytes distinguish booleans/floats from required integer fields.
    if canonical_json_bytes(config) != canonical_json_bytes(PROTOCOL):
        raise ValueError("configuration differs from the frozen preparation-policy-v1 profile")
    return config


def config_sha256(config: dict) -> str:
    return sha256_json(config)


def ordered(domain: str, values: list) -> list:
    return sorted(values, key=lambda v: (hashlib.sha256(f"{domain}|{v}".encode()).digest(), str(v)))


def build_schedule(config: dict, query_ids: list[int]) -> dict:
    if canonical_json_bytes(config) != canonical_json_bytes(PROTOCOL):
        raise ValueError("unfrozen schedule configuration")
    if len(query_ids) != 200 or len(set(query_ids)) != 200 or any(type(q) is not int or not 0 <= q < 10000 for q in query_ids):
        raise ValueError("schedule requires 200 distinct SIFT query IDs")
    keys = ordered("prep-block-v1", [f"{m}|{t}" for m in METHODS for t in FILTERS])
    builds = []
    for build in (1, 2):
        blocks = []
        for index, key in enumerate(keys if build == 1 else list(reversed(keys)), 1):
            method, threshold = key.split("|")
            blocks.append({
                "block_index": index, "method": method, "filter_threshold": int(threshold),
                "query_order_by_repetition": [ordered(f"prep-query-v1|{build}|{r}", query_ids) for r in range(1, 6)],
                "exposure_query_order": ordered(f"prep-exposure-v1|{build}", query_ids),
            })
        builds.append({"build_number": build, "arms": config["arms_by_build"][str(build)], "blocks": blocks})
    return {"protocol_id": config["protocol_id"], "builds": builds}


def read_settings(connection, names) -> dict[str, str]:
    with connection.cursor() as cursor:
        result = {}
        for name in names:
            cursor.execute("SELECT current_setting(%s)", (name,), prepare=False)
            result[name] = str(cursor.fetchone()[0])
    return result


def validate_server_settings(connection) -> dict[str, str]:
    observed = read_settings(connection, SERVER_CONTROLS)
    if observed != SERVER_CONTROLS:
        raise AssertionError(f"server settings differ from fixed design: {observed}")
    return observed


def configure_session(connection, method: str) -> tuple[int, dict[str, str]]:
    pid = configure_method_connection(connection, method)
    targets = {**SESSION_CONTROLS, "work_mem": "4MB" if method == "exact" else "64MB"}
    with connection.cursor() as cursor:
        for name, value in targets.items():
            cursor.execute("SELECT set_config(%s, %s, false)", (name, value), prepare=False)
    observed = {**session_settings(connection), **read_settings(connection, SESSION_CONTROLS)}
    if any(observed.get(name) != value for name, value in targets.items()):
        raise AssertionError(f"session settings differ from fixed design: {observed}")
    return pid, observed
