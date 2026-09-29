#!/usr/bin/env python3
"""Run one authorized Milestone 2 qualification stage and write immutable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .artifacts import (
    create_run_directory,
    finalize_complete,
    finalize_invalid,
    write_json_exclusive,
    write_jsonl_exclusive,
)
from .config import BenchmarkConfig, load_config, sha256_json
from .database import (
    configure_method_connection,
    connect,
    database_evidence,
    evict_shared_buffers,
    host_environment,
    load_scale,
    postgres_settings,
    search_parameters,
    search_sql,
    session_settings,
    source_stream_checksum,
    timed_execute_fetch,
    validate_source_samples,
    verify_versions,
)
from .dataset import (
    DEFAULT_HDF5_PATH,
    LOCAL_MANIFEST_PATH,
    SOURCE_MANIFEST_PATH,
    build_scale_manifest,
    ensure_scale_order,
    load_query_vectors,
    load_scale_vectors,
    select_query_ids,
    serializable_scale_manifest,
    validate_hdf5,
    validate_source_manifest_identity,
)
from .ground_truth import (
    generate_ground_truth,
    ground_truth_index,
    select_validation_keys,
    validate_ground_truth_numpy,
)
from .metrics import (
    canonical_recall_at_k,
    tie_aware_recall_at_k,
    validate_returned_results,
)
from .plans import audit_plan


ROOT = Path(__file__).resolve().parents[2]
STARTING_MILESTONE_1_COMMIT = "cd199a2b523b875ab06a8de00953e17672a2800a"


class RunLog:
    def __init__(self, path: Path) -> None:
        self._handle = path.open("x", encoding="utf-8", buffering=1)

    def write(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        line = f"{timestamp} {message}"
        print(line, flush=True)
        self._handle.write(line + "\n")

    def close(self) -> None:
        if not self._handle.closed:
            self.sync()
            self._handle.close()

    def sync(self) -> None:
        if not self._handle.closed:
            self._handle.flush()
            os.fsync(self._handle.fileno())


def git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=ROOT, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def git_state() -> dict[str, Any]:
    status = git_output("status", "--porcelain=v1")
    return {
        "commit": git_output("rev-parse", "HEAD"),
        "branch": git_output("branch", "--show-current"),
        "dirty": bool(status),
        "status_porcelain": status.splitlines(),
    }


def require_clean_git_state(state: dict[str, Any]) -> None:
    if bool(state.get("dirty")) or state.get("status_porcelain"):
        raise RuntimeError(
            "qualification runs require a clean committed Git state; commit source and "
            "prior append-only artifacts before launching"
        )


def verify_milestone1_preserved() -> dict[str, Any]:
    names = git_output(
        "ls-tree", "-r", "--name-only", STARTING_MILESTONE_1_COMMIT, "raw_results"
    ).splitlines()
    checked: dict[str, str] = {}
    for name in names:
        if not name or name.endswith(".gitkeep"):
            continue
        expected = subprocess.run(
            ["git", "show", f"{STARTING_MILESTONE_1_COMMIT}:{name}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        path = ROOT / name
        if not path.is_file() or path.read_bytes() != expected:
            raise AssertionError(f"tracked Milestone 1 evidence changed: {name}")
        checked[name] = hashlib.sha256(expected).hexdigest()
    return {
        "baseline_commit": STARTING_MILESTONE_1_COMMIT,
        "checked_files": checked,
        "preserved": True,
    }


def deterministic_order(domain: str, values: list[Any]) -> list[Any]:
    return sorted(
        values,
        key=lambda value: (
            hashlib.sha256(f"{domain}|{value}".encode("utf-8")).digest(),
            str(value),
        ),
    )


def build_schedule(config: BenchmarkConfig, timed_query_ids: list[int]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    block_index = 0
    for round_number in range(1, config.rounds + 1):
        block_domain = (
            f"m2-block-v1|{config.protocol['protocol_id']}|"
            f"{config.stage['stage_id']}|{round_number}|{config.scale_rows}"
        )
        block_keys = [
            f"{method}|{threshold}"
            for method in config.methods
            for threshold in config.filters
        ]
        ordered_keys = deterministic_order(block_domain, block_keys)
        for key in ordered_keys:
            block_index += 1
            method, threshold_text = key.split("|", maxsplit=1)
            threshold = int(threshold_text)
            repetitions: list[list[int]] = []
            for repetition in range(1, config.repetitions + 1):
                repetitions.append(
                    deterministic_order(
                        (
                            f"m2-query-order-v1|{config.protocol['protocol_id']}|"
                            f"{config.stage['stage_id']}|{round_number}|{config.scale_rows}|"
                            f"{method}|{threshold}|{repetition}"
                        ),
                        timed_query_ids,
                    )
                )
            blocks.append(
                {
                    "block_index": block_index,
                    "round": round_number,
                    "scale_rows": config.scale_rows,
                    "block_schedule_domain": block_domain,
                    "method": method,
                    "filter_threshold": threshold,
                    "query_order_by_repetition": repetitions,
                }
            )
    return {
        "algorithm": "ascending SHA-256 digest with stable textual tie-break",
        "protocol_id": config.protocol["protocol_id"],
        "stage_id": config.stage["stage_id"],
        "scale_rows": config.scale_rows,
        "rounds": config.rounds,
        "blocks": blocks,
    }


def summarize_executions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["method"]), int(row["filter_threshold"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for (method, threshold), group in sorted(groups.items()):
        successful = [row for row in group if row["error_type"] is None]
        per_query: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in successful:
            per_query[int(row["query_id"])].append(row)
        query_median_durations = [
            int(statistics.median(int(row["duration_ns"]) for row in query_rows))
            for query_rows in per_query.values()
        ]
        query_mean_canonical = [
            statistics.fmean(float(row["canonical_recall_at_10"]) for row in query_rows)
            for query_rows in per_query.values()
        ]
        query_mean_tie_aware = [
            statistics.fmean(float(row["tie_aware_recall_at_10"]) for row in query_rows)
            for query_rows in per_query.values()
        ]
        summaries.append(
            {
                "method": method,
                "filter_threshold": threshold,
                "execution_samples": len(group),
                "successful_executions": len(successful),
                "query_samples": len(per_query),
                "repetition_reduction": "median latency per query before condition summary",
                "median_latency_ns": int(statistics.median(query_median_durations))
                if query_median_durations
                else None,
                "minimum_query_median_latency_ns": min(query_median_durations)
                if query_median_durations
                else None,
                "maximum_query_median_latency_ns": max(query_median_durations)
                if query_median_durations
                else None,
                "p95_query_median_latency_ns": int(np.percentile(query_median_durations, 95))
                if query_median_durations
                else None,
                "mean_canonical_recall_at_10": statistics.fmean(query_mean_canonical)
                if query_mean_canonical
                else None,
                "mean_tie_aware_recall_at_10": statistics.fmean(query_mean_tie_aware)
                if query_mean_tie_aware
                else None,
                "returned_k_rate": sum(bool(row["returned_k"]) for row in group) / len(group),
            }
        )
    return summaries


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def build_resource_projection(
    config: BenchmarkConfig,
    phase_metrics: dict[str, Any],
    execution_rows: list[dict[str, Any]],
    relation_sizes: list[dict[str, Any]],
    run_dir: Path,
) -> dict[str, Any]:
    """Create a transparent, mechanical planning estimate from qualification evidence."""
    durations = [
        int(row["duration_ns"])
        for row in execution_rows
        if row.get("error_type") is None
    ]
    if not durations:
        raise AssertionError("cannot project resources without successful timed executions")
    final_scales = [int(value) for value in config.protocol["final_scales"]]
    final_rounds = int(config.protocol["final_execution"]["rounds"])
    linear_scale_round_factor = sum(
        scale / config.scale_rows for scale in final_scales
    ) * final_rounds
    projectable_phases = (
        "source_scale_read_ns",
        "copy_exact_ns",
        "copy_hnsw_from_exact_ns",
        "exact_index_ns",
        "hnsw_build_ns",
        "vacuum_analyze_checkpoint_ns",
        "ground_truth_generation_ns",
        "ground_truth_determinism_reexecution_ns",
        "independent_ground_truth_validation_ns",
        "shared_buffer_reset_ns",
    )
    observed_phase_ns = {
        name: int(phase_metrics[name]) for name in projectable_phases
    }
    projected_phase_seconds = {
        name: value * linear_scale_round_factor / 1_000_000_000
        for name, value in observed_phase_ns.items()
    }
    planned_timed = int(
        config.protocol["final_execution"]["planned_timed_executions"]
    )
    mean_duration = statistics.fmean(durations)
    query_only_seconds = mean_duration * planned_timed / 1_000_000_000

    current_timed_bytes = (run_dir / "executions.jsonl").stat().st_size
    current_warmup_bytes = (run_dir / "warmups.jsonl").stat().st_size
    current_ground_truth_bytes = (run_dir / "ground_truth.jsonl").stat().st_size
    current_plan_bytes = sum(
        path.stat().st_size for path in (run_dir / "plans").glob("*.json")
    )
    current_variable_bytes = (
        current_timed_bytes
        + current_warmup_bytes
        + current_ground_truth_bytes
        + current_plan_bytes
    )
    current_fixed_bytes = max(0, directory_size(run_dir) - current_variable_bytes)
    final_scale_rounds = len(final_scales) * final_rounds
    final_warmups = (
        final_scale_rounds
        * len(config.methods)
        * len(config.filters)
        * int(
            config.protocol["final_execution"][
                "warmup_queries_per_method_filter_block"
            ]
        )
    )
    final_ground_truth_records = (
        final_scale_rounds
        * int(config.protocol["ground_truth"]["query_count_per_scale"])
        * len(config.filters)
    )
    final_plan_count = final_scale_rounds * len(config.methods) * len(config.filters)
    warmup_projection_seconds = mean_duration * final_warmups / 1_000_000_000
    observed_other_overhead_ns = max(
        0,
        int(phase_metrics["total_before_final_artifacts_ns"])
        - sum(observed_phase_ns.values())
        - int(phase_metrics["timed_workload_and_warmups_ns"]),
    )
    other_overhead_projection_seconds = (
        observed_other_overhead_ns * final_scale_rounds / 1_000_000_000
    )

    def scaled_bytes(observed_bytes: int, observed_count: int, target_count: int) -> int:
        return int(round(observed_bytes / observed_count * target_count))

    estimated_artifact_bytes = (
        scaled_bytes(current_timed_bytes, len(execution_rows), planned_timed)
        + scaled_bytes(
            current_warmup_bytes,
            len(config.methods)
            * len(config.filters)
            * config.warmup_query_count
            * config.rounds,
            final_warmups,
        )
        + scaled_bytes(
            current_ground_truth_bytes,
            int(config.stage["expected_ground_truth_combinations"]),
            final_ground_truth_records,
        )
        + scaled_bytes(
            current_plan_bytes,
            len(config.methods) * len(config.filters),
            final_plan_count,
        )
        + current_fixed_bytes * final_scale_rounds
    )

    observed_relation_bytes = sum(int(row["relation_bytes"]) for row in relation_sizes)
    return {
        "projection_kind": "mechanical qualification planning estimate",
        "basis_stage": config.stage["stage_id"],
        "basis_scale_rows": config.scale_rows,
        "final_scales": final_scales,
        "final_rounds": final_rounds,
        "linear_scale_round_factor": linear_scale_round_factor,
        "observed_phase_ns": observed_phase_ns,
        "linearly_projected_phase_seconds": projected_phase_seconds,
        "query_latency_ns": {
            "minimum": min(durations),
            "mean": mean_duration,
            "maximum": max(durations),
        },
        "eventual_timed_execution_count": planned_timed,
        "query_only_projection_seconds_at_observed_scale": query_only_seconds,
        "warmup_projection_seconds_at_observed_scale": warmup_projection_seconds,
        "other_per_scale_round_overhead_projection_seconds": (
            other_overhead_projection_seconds
        ),
        "estimated_full_pipeline_seconds": sum(projected_phase_seconds.values())
        + query_only_seconds
        + warmup_projection_seconds
        + other_overhead_projection_seconds,
        "observed_relation_bytes": observed_relation_bytes,
        "estimated_1m_relation_bytes_linear": int(
            round(observed_relation_bytes * 1_000_000 / config.scale_rows)
        ),
        "observed_run_directory_bytes": directory_size(run_dir),
        "estimated_full_matrix_artifact_bytes": estimated_artifact_bytes,
        "artifact_projection_counts": {
            "timed_executions": planned_timed,
            "warmups": final_warmups,
            "ground_truth_records": final_ground_truth_records,
            "plans": final_plan_count,
            "scale_rounds": final_scale_rounds,
        },
        "limitations": [
            "phase times and relation bytes are scaled linearly with row count",
            "HNSW construction and query latency need not scale linearly",
            "query projection holds the observed qualification latency distribution fixed",
            "thermal drift, OS-cache state, and cross-round variation are not modeled",
            "estimate is for launch planning, not a bound or research measurement",
        ],
    }


def prepared_statement_evidence(connections: dict[str, Any], filter_count: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for method, connection in connections.items():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name, statement, parameter_types::text, generic_plans, custom_plans "
                "FROM pg_prepared_statements ORDER BY name",
                prepare=False,
            )
            rows = [
                {
                    "name": row[0],
                    "statement": row[1],
                    "parameter_types": row[2],
                    "generic_plans": row[3],
                    "custom_plans": row[4],
                }
                for row in cursor.fetchall()
                if "milestone2.sift_" in str(row[1])
            ]
        unique_search_statements = {row["statement"] for row in rows}
        if len(unique_search_statements) != filter_count:
            raise AssertionError(
                f"{method} has {len(unique_search_statements)} prepared search statements, expected {filter_count}"
            )
        if any(row["parameter_types"] != "{vector}" or row["custom_plans"] != 0 for row in rows):
            raise AssertionError(f"{method} must use one vector parameter and generic prepared plans")
        result[method] = rows
    return result


def energy_mode() -> dict[str, Any]:
    try:
        battery = subprocess.run(
            ["pmset", "-g", "batt"], text=True, capture_output=True, check=False
        )
        custom = subprocess.run(
            ["pmset", "-g", "custom"], text=True, capture_output=True, check=False
        )
    except OSError as error:
        confirmed = os.environ.get("M2_AC_POWER_CONFIRMED") == "1"
        return {
            "detection_method": "explicit M2_AC_POWER_CONFIRMED=1 fallback",
            "ac_power_detected": confirmed,
            "error": f"{type(error).__name__}: {error}",
            "ac_power_required_by_protocol": True,
        }
    ac_power_detected = (
        battery.returncode == 0 and "Now drawing from 'AC Power'" in battery.stdout
    )
    return {
        "detection_method": "pmset -g batt",
        "ac_power_detected": ac_power_detected,
        "battery_command": "pmset -g batt",
        "battery_returncode": battery.returncode,
        "battery_stdout": battery.stdout,
        "battery_stderr": battery.stderr,
        "energy_settings_command": "pmset -g custom",
        "energy_settings_returncode": custom.returncode,
        "energy_settings_stdout": custom.stdout,
        "energy_settings_stderr": custom.stderr,
        "ac_power_required_by_protocol": True,
    }


def verify_power_state(before: dict[str, Any], after: dict[str, Any]) -> None:
    if not before.get("ac_power_detected") or not after.get("ac_power_detected"):
        raise AssertionError("AC power was not present at both run boundaries")
    if before.get("energy_settings_stdout") != after.get("energy_settings_stdout"):
        raise AssertionError("power settings changed during the run")


def run_stage(config_path: Path, dataset_path: Path) -> Path:
    config = load_config(config_path)
    before_run_git = git_state()
    require_clean_git_state(before_run_git)
    run_dir = create_run_directory(config.config_sha256)
    run_id = run_dir.name
    log = RunLog(run_dir / "run.log")
    total_started = time.perf_counter_ns()
    last_phase = "initialization"
    open_connections: list[Any] = []

    try:
        log.write(
            f"starting {config.stage['stage_id']} at scale={config.scale_rows}; "
            f"expected timed executions={config.expected_execution_count}"
        )
        if config.expected_execution_count != int(config.stage["expected_timed_executions"]):
            raise AssertionError("stage expected execution count is inconsistent with configuration")

        milestone1 = verify_milestone1_preserved()
        source_manifest = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
        source_manifest_validation = validate_source_manifest_identity(
            source_manifest, config.protocol["dataset"]
        )
        write_json_exclusive(run_dir / "config.json", config.combined)
        write_json_exclusive(
            run_dir / "run_manifest.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "stage_id": config.stage["stage_id"],
                "config_sha256": config.config_sha256,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "git_at_start": before_run_git,
                "milestone1_preservation": milestone1,
                "qualification_only": True,
                "research_conclusion_authorized": False,
            },
        )

        last_phase = "power_state_validation"
        power_at_start = energy_mode()
        write_json_exclusive(run_dir / "power_state.json", power_at_start)
        if not power_at_start["ac_power_detected"]:
            raise AssertionError(
                "AC power is required by the frozen protocol; connect power or explicitly "
                "confirm a non-macOS host with M2_AC_POWER_CONFIRMED=1"
            )

        last_phase = "dataset_validation"
        log.write(f"validating SIFT1M artifact {dataset_path}")
        dataset_manifest = validate_hdf5(
            dataset_path,
            expected_sha256=str(config.protocol["dataset"]["expected_sha256"]),
        )
        if dataset_manifest["byte_size"] != int(config.protocol["dataset"]["expected_bytes"]):
            raise AssertionError("SIFT1M byte size does not match the frozen protocol")
        acquisition = (
            json.loads(LOCAL_MANIFEST_PATH.read_text(encoding="utf-8"))
            if LOCAL_MANIFEST_PATH.exists()
            else {"download_timestamp": "unavailable", "reason": "local manifest missing"}
        )
        dataset_manifest.update(
            {
                "canonical_source": source_manifest,
                "source_manifest_identity_validation": source_manifest_validation,
                "local_acquisition": acquisition,
                "full_scale_supplied_neighbor_validation": "deferred until authorized 1M stage",
            }
        )
        write_json_exclusive(run_dir / "dataset_manifest.json", dataset_manifest)

        last_phase = "deterministic_selection"
        log.write("constructing/reusing global one-million-ID SHA-256 scale order")
        scale_assignment = config.protocol["scale_assignment"]
        global_order, order_manifest = ensure_scale_order(
            base_count=int(scale_assignment["base_count"]),
            expected_ordered_ids_sha256=str(
                scale_assignment["expected_ordered_ids_sha256"]
            ),
            expected_cache_sha256=str(scale_assignment["expected_cache_sha256"]),
        )
        scale_manifest = build_scale_manifest(global_order, config.scale_rows, config.filters)
        serial_scale = {
            **serializable_scale_manifest(scale_manifest),
            "global_order": order_manifest,
        }
        scale_manifest_sha = sha256_json(serial_scale)
        serial_scale["scale_manifest_sha256"] = scale_manifest_sha
        write_json_exclusive(run_dir / "scale_manifest.json", serial_scale)
        filter_counts = {
            str(threshold): int(scale_manifest["filter_counts"][str(threshold)])
            for threshold in config.filters
        }
        write_json_exclusive(run_dir / "filter_counts.json", filter_counts)

        query_manifest = select_query_ids()
        all_query_ids = query_manifest["measured_query_ids"] + query_manifest["warmup_query_ids"]
        query_vectors = load_query_vectors(dataset_path, all_query_ids)
        query_manifest["vector_sha256"] = {
            str(query_id): hashlib.sha256(
                np.asarray(query_vectors[query_id], dtype="<f4").tobytes()
            ).hexdigest()
            for query_id in all_query_ids
        }
        timed_query_ids = query_manifest["measured_query_ids"][: config.measured_query_count]
        query_manifest["qualification_timed_query_ids"] = timed_query_ids
        write_json_exclusive(run_dir / "queries.json", query_manifest)
        schedule = build_schedule(config, timed_query_ids)
        write_json_exclusive(run_dir / "schedule.json", schedule)

        last_phase = "scale_materialization"
        log.write(f"reading {config.scale_rows} globally selected SIFT base vectors")
        phase_metrics: dict[str, Any] = {}
        started = time.perf_counter_ns()
        scale_vectors = load_scale_vectors(dataset_path, scale_manifest["selected_base_ids"])
        phase_metrics["source_scale_read_ns"] = time.perf_counter_ns() - started
        selected_buckets = {
            int(identifier): int(bucket)
            for identifier, bucket in zip(
                scale_manifest["selected_base_ids"], scale_manifest["filter_buckets"], strict=True
            )
        }

        last_phase = "database_load_and_index"
        preparation = connect(application_name=f"m2-{config.stage['stage_id']}-prepare")
        open_connections.append(preparation)
        versions = verify_versions(preparation)
        if (
            versions["postgresql_version"] != config.protocol["postgresql_version"]
            or versions["postgresql_version_num"] != "170011"
            or versions["pgvector_version"] != config.protocol["pgvector_version"]
        ):
            raise AssertionError(f"database version mismatch: {versions}")
        host_at_start = host_environment()
        resource_snapshots = [
            {"phase": "before_database_load", "host": host_at_start}
        ]
        write_json_exclusive(
            run_dir / "environment.json",
            {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "host": host_at_start,
                "database_versions": versions,
                "database_connection": {
                    "host": os.environ.get("PGHOST", "127.0.0.1"),
                    "port": int(os.environ.get("PGPORT", "55432")),
                    "database": os.environ.get("PGDATABASE", "filtered_vector_search"),
                    "transport": "TCP loopback",
                },
            },
        )
        log.write("loading exact/HNSW tables and building indexes")
        phase_metrics.update(
            load_scale(
                preparation,
                base_ids=scale_manifest["selected_base_ids"],
                vectors=scale_vectors,
                buckets=scale_manifest["filter_buckets"],
                hnsw_build_settings=config.protocol["hnsw"],
            )
        )
        evidence = database_evidence(
            preparation, scale_rows=config.scale_rows, thresholds=config.filters
        )
        source_checksum = source_stream_checksum(
            scale_manifest["selected_base_ids"], scale_vectors, scale_manifest["filter_buckets"]
        )
        if source_checksum != evidence["ordered_vector_stream_sha256"]:
            raise AssertionError("loaded IDs/ranks/buckets/vectors differ from the canonical SIFT source")
        evidence["source_vector_stream_sha256"] = source_checksum
        evidence["all_source_rows_equal"] = True
        sample_validation = validate_source_samples(
            preparation,
            base_ids=scale_manifest["selected_base_ids"],
            vectors=scale_vectors,
            sample_count=100,
        )
        write_json_exclusive(run_dir / "database_evidence.json", evidence)
        write_json_exclusive(run_dir / "relation_sizes.json", evidence["relation_sizes"])
        write_json_exclusive(run_dir / "source_vector_samples.json", sample_validation)
        write_json_exclusive(run_dir / "postgres_settings.json", postgres_settings(preparation))
        resource_snapshots.append(
            {"phase": "after_database_load_and_indexes", "host": host_environment()}
        )

        last_phase = "ground_truth"
        configure_method_connection(preparation, "exact")
        log.write("generating 1,000 durable PostgreSQL exact ground-truth records")
        integer_counts = {int(key): int(value) for key, value in filter_counts.items()}
        ground_truth_records, ground_truth_ns = generate_ground_truth(
            preparation,
            run_id=run_id,
            scale_rows=config.scale_rows,
            thresholds=config.filters,
            qualifying_counts=integer_counts,
            query_ids=query_manifest["measured_query_ids"][: config.ground_truth_query_count],
            query_vectors=query_vectors,
            k=config.k,
            dataset_sha256=dataset_manifest["sha256"],
            scale_manifest_sha256=scale_manifest_sha,
        )
        phase_metrics["ground_truth_generation_ns"] = ground_truth_ns
        if len(ground_truth_records) != int(config.stage["expected_ground_truth_combinations"]):
            raise AssertionError("ground-truth record count is incomplete")
        write_jsonl_exclusive(run_dir / "ground_truth.jsonl", ground_truth_records)
        gt_index = ground_truth_index(ground_truth_records)

        log.write("re-executing all 1,000 exact ground-truth combinations for determinism")
        repeated_ground_truth, repeated_ground_truth_ns = generate_ground_truth(
            preparation,
            run_id=run_id,
            scale_rows=config.scale_rows,
            thresholds=config.filters,
            qualifying_counts=integer_counts,
            query_ids=query_manifest["measured_query_ids"][: config.ground_truth_query_count],
            query_vectors=query_vectors,
            k=config.k,
            dataset_sha256=dataset_manifest["sha256"],
            scale_manifest_sha256=scale_manifest_sha,
        )
        phase_metrics["ground_truth_determinism_reexecution_ns"] = repeated_ground_truth_ns
        original_checksums = [record["record_sha256"] for record in ground_truth_records]
        repeated_checksums = [record["record_sha256"] for record in repeated_ground_truth]
        if original_checksums != repeated_checksums:
            raise AssertionError("exact ground truth changed during deterministic re-execution")
        write_json_exclusive(
            run_dir / "ground_truth_reexecution.json",
            {
                "reexecuted_records": len(repeated_ground_truth),
                "record_checksums_identical_in_order": True,
                "duration_ns": repeated_ground_truth_ns,
                "passed": True,
            },
        )

        validation_keys = select_validation_keys(
            query_manifest["measured_query_ids"][: config.ground_truth_query_count],
            config.filters,
            int(config.stage["independent_validation_count"]),
        )
        started = time.perf_counter_ns()
        independent_validation = validate_ground_truth_numpy(
            records=gt_index,
            validation_keys=validation_keys,
            base_ids=scale_manifest["selected_base_ids"],
            vectors=scale_vectors,
            buckets=scale_manifest["filter_buckets"],
            query_vectors=query_vectors,
            k=config.k,
        )
        phase_metrics["independent_ground_truth_validation_ns"] = (
            time.perf_counter_ns() - started
        )
        write_json_exclusive(
            run_dir / "ground_truth_validation.json", independent_validation
        )
        resource_snapshots.append(
            {"phase": "after_ground_truth_validation", "host": host_environment()}
        )

        last_phase = "shared_buffer_reset"
        log.write(
            "evicting PostgreSQL shared buffers after CHECKPOINT; OS cache is not flushed"
        )
        started = time.perf_counter_ns()
        cache_reset = evict_shared_buffers(preparation)
        phase_metrics["shared_buffer_reset_ns"] = time.perf_counter_ns() - started
        write_json_exclusive(run_dir / "cache_reset.json", cache_reset)
        preparation.close()
        open_connections.remove(preparation)

        last_phase = "persistent_sessions"
        connections: dict[str, Any] = {}
        backend_pids: dict[str, int] = {}
        settings_by_method: dict[str, dict[str, str]] = {}
        for method in config.methods:
            connection = connect(
                application_name=f"m2-{config.stage['stage_id']}-{method}"
            )
            open_connections.append(connection)
            connections[method] = connection
            backend_pids[method] = configure_method_connection(connection, method)
            settings_by_method[method] = session_settings(connection)
        write_json_exclusive(
            run_dir / "method_sessions.json",
            {"backend_pids": backend_pids, "settings": settings_by_method},
        )

        last_phase = "plan_audit"
        plan_records: list[dict[str, Any]] = []
        plan_ids: dict[tuple[str, int], str] = {}
        audit_query_id = int(timed_query_ids[0])
        log.write("capturing 15 untimed plan audits before the defined warm-up")
        for method in config.methods:
            for threshold in config.filters:
                plan_id, document, record = audit_plan(
                    connections[method],
                    method=method,
                    threshold=threshold,
                    query_id=audit_query_id,
                    query_vector=query_vectors[audit_query_id],
                    k=config.k,
                    scale_rows=config.scale_rows,
                )
                record.update(
                    {
                        "backend_pid": backend_pids[method],
                        "raw_plan_path": f"plans/{plan_id}.json",
                    }
                )
                write_json_exclusive(run_dir / "plans" / f"{plan_id}.json", document)
                plan_records.append(record)
                plan_ids[(method, threshold)] = plan_id
        write_jsonl_exclusive(run_dir / "plan_assertions.jsonl", plan_records)
        plan_failures = [record for record in plan_records if not record["passed"]]
        if plan_failures:
            raise AssertionError(f"{len(plan_failures)} method/filter plan audits failed")

        last_phase = "warmup_and_timing"
        warmup_records: list[dict[str, Any]] = []
        execution_rows: list[dict[str, Any]] = []
        sequence_index = 0
        workload_started = time.perf_counter_ns()
        for block in schedule["blocks"]:
            round_number = int(block["round"])
            method = str(block["method"])
            threshold = int(block["filter_threshold"])
            sql = search_sql(method, threshold, config.k)
            sql_sha256 = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            connection = connections[method]
            log.write(
                f"block {block['block_index']}/{len(schedule['blocks'])} "
                f"round={round_number} method={method} filter={threshold}: "
                f"{config.warmup_query_count} warm-ups, {config.repetitions} timed rounds"
            )
            with connection.cursor() as cursor:
                for query_id in query_manifest["warmup_query_ids"][: config.warmup_query_count]:
                    cursor.execute(
                        sql,
                        search_parameters(method, query_vectors[int(query_id)]),
                        prepare=True,
                    )
                    rows = [(int(row[0]), float(row[1])) for row in cursor.fetchall()]
                    validation = validate_returned_results(
                        [row[0] for row in rows],
                        [row[1] for row in rows],
                        k=config.k,
                        selected_buckets=selected_buckets,
                        threshold=threshold,
                    )
                    if not all(
                        validation[key]
                        for key in ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")
                    ):
                        raise AssertionError("warm-up result validation failed")
                    warmup_records.append(
                        {
                            "schema_version": 1,
                            "run_id": run_id,
                            "block_index": block["block_index"],
                            "round": round_number,
                            "scale_rows": config.scale_rows,
                            "build_id": f"{run_id}-round-{round_number}-build-1",
                            "method": method,
                            "filter_threshold": threshold,
                            "query_id": int(query_id),
                            "backend_pid": backend_pids[method],
                            "result_ids": [row[0] for row in rows],
                            "distances": [row[1] for row in rows],
                            **validation,
                        }
                    )

                for repetition, ordered_queries in enumerate(
                    block["query_order_by_repetition"], start=1
                ):
                    block_buffer: list[dict[str, Any]] = []
                    for query_id in ordered_queries:
                        sequence_index += 1
                        timed = timed_execute_fetch(
                            cursor,
                            sql,
                            search_parameters(method, query_vectors[int(query_id)]),
                        )
                        ids = [row[0] for row in timed.rows]
                        distances = [row[1] for row in timed.rows]
                        if timed.error_type is None:
                            validation = validate_returned_results(
                                ids,
                                distances,
                                k=config.k,
                                selected_buckets=selected_buckets,
                                threshold=threshold,
                            )
                            truth = gt_index[(int(query_id), threshold)]
                            canonical_recall = canonical_recall_at_k(
                                ids, truth["canonical_ids"], config.k
                            )
                            tie_recall = tie_aware_recall_at_k(
                                ids,
                                truth["strictly_closer_ids"],
                                truth["boundary_tie_ids"],
                                config.k,
                            )
                        else:
                            validation = {
                                "returned_count": 0,
                                "returned_k": False,
                                "shortfall": config.k,
                                "ids_unique": False,
                                "scale_valid": False,
                                "filter_valid": False,
                                "distance_order_valid": False,
                            }
                            truth = gt_index[(int(query_id), threshold)]
                            canonical_recall = None
                            tie_recall = None
                        row = {
                            "schema_version": 1,
                            "run_id": run_id,
                            "config_sha256": config.config_sha256,
                            "stage_id": config.stage["stage_id"],
                            "sequence_index": sequence_index,
                            "block_index": block["block_index"],
                            "round": round_number,
                            "scale_rows": config.scale_rows,
                            "build_id": f"{run_id}-round-{round_number}-build-1",
                            "method": method,
                            "filter_threshold": threshold,
                            "target_selectivity": threshold / 100,
                            "qualifying_count": integer_counts[threshold],
                            "query_id": int(query_id),
                            "repetition": repetition,
                            "k": config.k,
                            "backend_pid": backend_pids[method],
                            "prepared": True,
                            "logical_prepared_statement": f"{method}_filter_{threshold}",
                            "sql_sha256": sql_sha256,
                            "duration_ns": timed.duration_ns,
                            **validation,
                            "result_ids": ids,
                            "distances": distances,
                            "canonical_recall_at_10": canonical_recall,
                            "tie_aware_recall_at_10": tie_recall,
                            "ground_truth_record_sha256": truth["record_sha256"],
                            "timeout": timed.error_type == "QueryCanceled",
                            "error_type": timed.error_type,
                            "error_message": timed.error_message,
                            "plan_audit_id": plan_ids[(method, threshold)],
                        }
                        block_buffer.append(row)
                    execution_rows.extend(block_buffer)
        phase_metrics["timed_workload_and_warmups_ns"] = time.perf_counter_ns() - workload_started
        resource_snapshots.append(
            {"phase": "after_timed_workload", "host": host_environment()}
        )

        write_jsonl_exclusive(run_dir / "warmups.jsonl", warmup_records)
        write_jsonl_exclusive(run_dir / "executions.jsonl", execution_rows)
        prepared_evidence = prepared_statement_evidence(connections, len(config.filters))
        write_json_exclusive(run_dir / "prepared_statements.json", prepared_evidence)

        for connection in list(open_connections):
            connection.close()
            open_connections.remove(connection)

        last_phase = "final_validation"
        final_validation_started = time.perf_counter_ns()
        expected_keys = {
            (round_number, method, threshold, query_id, repetition)
            for round_number in range(1, config.rounds + 1)
            for method in config.methods
            for threshold in config.filters
            for query_id in timed_query_ids
            for repetition in range(1, config.repetitions + 1)
        }
        observed_keys = {
            (
                int(row["round"]),
                str(row["method"]),
                int(row["filter_threshold"]),
                int(row["query_id"]),
                int(row["repetition"]),
            )
            for row in execution_rows
        }
        if len(execution_rows) != config.expected_execution_count or observed_keys != expected_keys:
            raise AssertionError("measured execution matrix is incomplete or duplicated")
        errors = [row for row in execution_rows if row["error_type"] is not None]
        invalid_results = [
            row
            for row in execution_rows
            if row["error_type"] is None
            and not all(
                row[key]
                for key in ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")
            )
        ]
        invalid_exact = [
            row
            for row in execution_rows
            if row["method"] == "exact"
            and (
                not row["returned_k"]
                or row["canonical_recall_at_10"] != 1.0
                or row["tie_aware_recall_at_10"] != 1.0
            )
        ]
        if errors or invalid_results or invalid_exact:
            raise AssertionError(
                f"execution validation failed: errors={len(errors)}, "
                f"invalid_results={len(invalid_results)}, invalid_exact={len(invalid_exact)}"
            )
        if len(warmup_records) != (
            config.rounds
            * len(config.methods)
            * len(config.filters)
            * config.warmup_query_count
        ):
            raise AssertionError("warm-up execution matrix is incomplete")

        summaries = summarize_executions(execution_rows)
        write_json_exclusive(run_dir / "summary.json", summaries)
        phase_metrics["final_validation_ns"] = (
            time.perf_counter_ns() - final_validation_started
        )
        phase_metrics["total_before_final_artifacts_ns"] = time.perf_counter_ns() - total_started
        write_json_exclusive(run_dir / "phase_metrics.json", phase_metrics)

        projection = build_resource_projection(
            config,
            phase_metrics,
            execution_rows,
            evidence["relation_sizes"],
            run_dir,
        )
        host_after = host_environment()
        resource_snapshots.append({"phase": "after_final_validation", "host": host_after})
        resources = {
            "host_at_start": host_at_start,
            "host_after": host_after,
            "phase_snapshots": resource_snapshots,
            "minimum_observed_memory_available_bytes": min(
                int(snapshot["host"]["memory_available_bytes"])
                for snapshot in resource_snapshots
            ),
            "maximum_observed_memory_pressure_from_start_bytes": max(
                0,
                int(host_at_start["memory_available_bytes"])
                - min(
                    int(snapshot["host"]["memory_available_bytes"])
                    for snapshot in resource_snapshots
                ),
            ),
            "minimum_observed_disk_free_bytes": min(
                int(snapshot["host"]["disk_free_bytes"])
                for snapshot in resource_snapshots
            ),
            "memory_available_change_bytes": (
                int(host_after["memory_available_bytes"])
                - int(host_at_start["memory_available_bytes"])
            ),
            "disk_free_change_bytes": (
                int(host_after["disk_free_bytes"])
                - int(host_at_start["disk_free_bytes"])
            ),
            "energy_mode_at_start": power_at_start,
            "energy_mode_after": energy_mode(),
            "run_directory_bytes_before_resource_artifact": directory_size(run_dir),
            "projection": projection,
        }
        write_json_exclusive(run_dir / "resource_observations.json", resources)
        verify_power_state(power_at_start, resources["energy_mode_after"])

        validation_report = {
            "schema_version": 1,
            "run_id": run_id,
            "passed": True,
            "checks": {
                "milestone1_preserved": True,
                "dataset_checksum_shapes_dtypes_finite": True,
                "database_versions": versions,
                "physical_scale_rows": config.scale_rows,
                "exact_filter_counts": filter_counts,
                "table_equivalence": True,
                "source_vector_sample_count": sample_validation["sample_count"],
                "ground_truth_records": len(ground_truth_records),
                "ground_truth_deterministic_reexecutions": len(repeated_ground_truth),
                "independent_ground_truth_checks": independent_validation[
                    "validated_combination_count"
                ],
                "plan_audits": len(plan_records),
                "plan_failures": 0,
                "warmups": len(warmup_records),
                "timed_executions": len(execution_rows),
                "execution_errors": 0,
                "prepared_statement_groups": {
                    method: len({row["statement"] for row in rows})
                    for method, rows in prepared_evidence.items()
                },
                "full_1m_supplied_neighbor_check": "deferred by stop condition",
            },
            "qualification_measurements_are_research_findings": False,
        }
        write_json_exclusive(run_dir / "validation_report.json", validation_report)
        log.write("all hard qualification gates passed; finalizing checksums")
        log.sync()
        finalize_complete(
            run_dir,
            {
                "schema_version": 1,
                "run_id": run_id,
                "stage_id": config.stage["stage_id"],
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "valid": True,
                "qualification_only": True,
                "timed_executions": len(execution_rows),
                "research_conclusion_authorized": False,
            },
        )
        log.close()
        print(run_dir)
        return run_dir
    except BaseException as error:
        for connection in open_connections:
            try:
                connection.close()
            except BaseException:
                pass
        try:
            log.write(f"run invalid during {last_phase}: {type(error).__name__}: {error}")
            log.write(traceback.format_exc())
        finally:
            log.close()
        try:
            write_json_exclusive(
                run_dir / "failure.json",
                {
                    "phase": last_phase,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "traceback": traceback.format_exc(),
                },
            )
            finalize_invalid(
                run_dir,
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "stage_id": config.stage["stage_id"],
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "last_phase": last_phase,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
        except BaseException as finalization_error:
            print(f"failed to finalize invalid run: {finalization_error}", file=sys.stderr)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_HDF5_PATH)
    args = parser.parse_args()
    run_stage(args.config, args.dataset)


if __name__ == "__main__":
    main()
