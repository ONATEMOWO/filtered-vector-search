"""Execute only the frozen, bounded 100k preparation-policy campaign.

Historical Milestone 2 profiles and raw artifacts are never modified. The two
arms share one physical graph within each build. Shared-buffer eviction is an
explicit operational reset, not a server restart or a cold OS-cache claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from experiments.milestone2.artifacts import (
    finalize_complete, finalize_invalid, make_run_id, sha256_file,
    write_json_exclusive, write_jsonl_exclusive,
)
from experiments.milestone2.config import read_json, sha256_json, validate_config
from experiments.milestone2.database import (
    connect, database_evidence, evict_shared_buffers, host_environment, load_scale,
    postgres_settings, search_parameters, search_sql, source_stream_checksum,
    session_settings, timed_execute_fetch, validate_source_samples, verify_versions,
)
from experiments.milestone2.dataset import (
    DEFAULT_HDF5_PATH, SOURCE_MANIFEST_PATH, build_scale_manifest, ensure_scale_order,
    load_query_vectors, load_scale_vectors, select_query_ids,
    serializable_scale_manifest, validate_hdf5, validate_source_manifest_identity,
)
from experiments.milestone2.ground_truth import (
    generate_ground_truth, ground_truth_index, select_validation_keys,
    validate_ground_truth_numpy,
)
from experiments.milestone2.metrics import (
    canonical_recall_at_k, tie_aware_recall_at_k, validate_returned_results,
)
from experiments.milestone2.plans import audit_plan
from experiments.milestone2.restart import capture_restart_identity, validate_identity_continuity
from experiments.milestone2.runner import (
    RunLog, energy_mode, git_state, prepared_statement_evidence,
    require_clean_git_state, verify_milestone1_preserved, verify_power_state,
)
from .journal import CheckpointJournal
from .protocol import (
    FILTERS, K, METHODS, PROTOCOL_PATH, ROOT, SCALE_ROWS, SESSION_CONTROLS, build_schedule,
    config_sha256, configure_session, load_protocol, read_settings, validate_server_settings,
)


RUNS_ROOT = ROOT / "raw_results" / "preparation_policy"
LOCK_KEY = 73120412026
VALIDITY_FLAGS = ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")


def source_identity() -> dict[str, str]:
    """Hash all tracked experiment dependencies, not just this entry point."""
    completed = subprocess.run(
        ["git", "ls-files", "--", "experiments", "sql", "config", "tests", "requirements-milestone2.txt",
         "data/sift1m/source_manifest.json"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    return {name: sha256_file(ROOT / name) for name in completed.stdout.splitlines()}


def acquire_campaign_lock(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,), prepare=False)
        if cursor.fetchone()[0] is not True:
            raise RuntimeError("another preparation-policy campaign holds the advisory lock")


def guard_other_clients(connection: Any, allowed_pids: Iterable[int] = ()) -> list[dict[str, Any]]:
    """Fail closed before cluster-wide buffer eviction or benchmark table reload."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pid, datname, application_name, state FROM pg_stat_activity "
            "WHERE backend_type = 'client backend' AND pid <> pg_backend_pid() "
            "ORDER BY pid", prepare=False,
        )
        observed = [{"pid": int(p), "database": d, "application_name": a, "state": s}
                    for p, d, a, s in cursor.fetchall()]
    foreign = [row for row in observed if row["pid"] not in set(allowed_pids)]
    if foreign:
        raise RuntimeError(f"other client sessions prevent an isolated reset/load: {foreign}")
    return observed


def assert_distinct_builds(first: dict, second: dict) -> None:
    for field in ("system_identifier", "database", "server_version_num"):
        if first[field] != second[field]:
            raise AssertionError(f"builds changed cluster identity: {field}")
    previous = {row["relation"]: row for row in first["relations"]}
    if set(previous) != {row["relation"] for row in second["relations"]}:
        raise AssertionError("build relation set changed")
    for row in second["relations"]:
        old = previous[row["relation"]]
        if row["oid"] == old["oid"] or row["filenode"] == old["filenode"]:
            raise AssertionError("physical table/index reused across builds")


def assert_same_arm_identity(before: dict, after: dict) -> None:
    validate_identity_continuity(before, after)
    if before["postmaster_started_at"] != after["postmaster_started_at"]:
        raise AssertionError("server restarted during a shared-buffer-reset arm")


def assert_prepared_counts(evidence: dict, arm: str) -> None:
    expected = 1022 if arm == "A" else 1222 if arm == "B" else None
    if expected is None or set(evidence) != set(METHODS):
        raise AssertionError("invalid arm/prepared statement methods")
    for method in METHODS:
        rows = evidence[method]
        expected_sql = {search_sql(method, t, K).replace("%s", "$1") for t in FILTERS}
        if len(rows) != 5 or {r["statement"] for r in rows} != expected_sql:
            raise AssertionError("prepared statement SQL/filter matrix differs")
        if any(r["generic_plans"] != expected or r["custom_plans"] != 0
               or r["parameter_types"] != "{vector}" for r in rows):
            raise AssertionError(f"arm {arm} requires exactly {expected} generic executions per statement")


def capture_method_settings(connections: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {method: {**session_settings(connection), **read_settings(connection, SESSION_CONTROLS)}
            for method, connection in connections.items()}


def assert_unchanged_settings(before: dict, after: dict) -> None:
    if set(before) != set(METHODS) or after != before:
        raise AssertionError("method session settings changed during arm")


def assert_valid_row(row: dict) -> None:
    if (row["error_type"] is not None or row["error_message"] is not None or row["timeout"]
            or type(row["duration_ns"]) is not int or row["duration_ns"] <= 0
            or not all(row[key] for key in VALIDITY_FLAGS)):
        raise AssertionError("query failed or returned invalid results; observation preserved")
    if row["method"] == "exact":
        if not row["returned_k"]:
            raise AssertionError("exact search returned fewer than k")
        if row["phase"] != "disjoint_warmup" and (
            row["canonical_recall_at_10"] != 1.0 or row["tie_aware_recall_at_10"] != 1.0
        ):
            raise AssertionError("exact measured-query result differs from ground truth")


def observation(
    *, cursor: Any, vector: np.ndarray, base: dict, sequence_index: int,
    selected_buckets: dict[int, int], truth: dict | None,
) -> dict:
    method, threshold = base["method"], base["filter_threshold"]
    sql = search_sql(method, threshold, K)
    started = time.perf_counter_ns()
    timed = timed_execute_fetch(cursor, sql, search_parameters(method, vector))
    ids = [row[0] for row in timed.rows]
    distances = [row[1] for row in timed.rows]
    validation = validate_returned_results(
        ids, distances, k=K, selected_buckets=selected_buckets, threshold=threshold,
    )
    canonical = tie = None
    if truth is not None and timed.error_type is None:
        canonical = canonical_recall_at_k(ids, truth["canonical_ids"], K)
        tie = tie_aware_recall_at_k(ids, truth["strictly_closer_ids"], truth["boundary_tie_ids"], K)
    return {
        **base, "schema_version": 1, "sequence_index": sequence_index,
        "start_monotonic_ns": started, "duration_ns": timed.duration_ns,
        "scale_rows": SCALE_ROWS, "k": K, "prepared": True,
        "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "result_ids": ids, "distances": distances, **validation,
        "canonical_recall_at_10": canonical, "tie_aware_recall_at_10": tie,
        "ground_truth_record_sha256": None if truth is None else truth["record_sha256"],
        "error_type": timed.error_type, "error_message": timed.error_message,
        "timeout": timed.error_type == "QueryCanceled",
    }


def create_run(config: dict) -> Path:
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    destination = RUNS_ROOT / make_run_id(config_sha256(config))
    destination.mkdir(exist_ok=False)
    (destination / "plans").mkdir()
    (destination / "ACTIVE").touch(exist_ok=False)
    return destination


def run_campaign(config_path: Path, dataset_path: Path) -> Path:
    config = load_protocol(config_path)
    initial_git = git_state()
    require_clean_git_state(initial_git)
    initial_source = source_identity()
    run_dir = create_run(config)
    run_id, digest = run_dir.name, config_sha256(config)
    journal = CheckpointJournal(run_dir)
    log = RunLog(run_dir / "run.log")
    opened: list[Any] = []
    concurrency_checks: list[dict[str, Any]] = []
    last_phase = "initialization"
    sequence_index = 0
    campaign_start = time.perf_counter_ns()
    try:
        log.write("Starting bounded preparation-policy campaign: 100k, two builds, four arms")
        source_protocol = read_json(ROOT / config["source_protocol"])
        validate_config(source_protocol, read_json(ROOT / "config/milestone2/qualification-100k.json"))
        write_json_exclusive(run_dir / "config.json", config)
        write_json_exclusive(run_dir / "manifest.json", {
            "schema_version": 1, "run_id": run_id, "protocol_id": config["protocol_id"],
            "config_sha256": digest, "git_at_start": initial_git,
            "source_file_sha256": initial_source, "source_protocol": source_protocol,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "milestone1_preservation": verify_milestone1_preserved(),
            "research_conclusion_authorized": False,
        })
        power_before = energy_mode()
        write_json_exclusive(run_dir / "power_before.json", power_before)
        if not power_before["ac_power_detected"]:
            raise AssertionError("AC power required before campaign")
        last_phase = "source_validation"
        source_manifest = read_json(SOURCE_MANIFEST_PATH)
        source_validation = validate_source_manifest_identity(source_manifest, source_protocol["dataset"])
        dataset = validate_hdf5(dataset_path, expected_sha256=source_protocol["dataset"]["expected_sha256"])
        if dataset["byte_size"] != source_protocol["dataset"]["expected_bytes"]:
            raise AssertionError("dataset size differs from frozen source")
        dataset.update({"canonical_source": source_manifest, "source_manifest_identity_validation": source_validation})
        write_json_exclusive(run_dir / "dataset_manifest.json", dataset)
        assignment = source_protocol["scale_assignment"]
        order, order_manifest = ensure_scale_order(
            base_count=assignment["base_count"],
            expected_ordered_ids_sha256=assignment["expected_ordered_ids_sha256"],
            expected_cache_sha256=assignment["expected_cache_sha256"],
        )
        scale = build_scale_manifest(order, SCALE_ROWS, FILTERS)
        serial_scale = {**serializable_scale_manifest(scale), "global_order": order_manifest}
        scale_digest = sha256_json(serial_scale)
        serial_scale["scale_manifest_sha256"] = scale_digest
        write_json_exclusive(run_dir / "scale_manifest.json", serial_scale)
        queries = select_query_ids()
        all_ids = queries["measured_query_ids"] + queries["warmup_query_ids"]
        query_vectors = load_query_vectors(dataset_path, all_ids)
        queries["vector_sha256"] = {
            str(q): hashlib.sha256(np.asarray(query_vectors[q], dtype="<f4").tobytes()).hexdigest()
            for q in all_ids
        }
        write_json_exclusive(run_dir / "queries.json", queries)
        schedule = build_schedule(config, queries["measured_query_ids"])
        write_json_exclusive(run_dir / "schedule.json", schedule)
        vectors = load_scale_vectors(dataset_path, scale["selected_base_ids"])
        selected_buckets = {int(i): int(b) for i, b in zip(scale["selected_base_ids"], scale["filter_buckets"], strict=True)}
        counts = {int(k): int(v) for k, v in scale["filter_counts"].items()}
        source_checksum = source_stream_checksum(scale["selected_base_ids"], vectors, scale["filter_buckets"])
        control = connect(application_name="preparation-policy-control")
        opened.append(control)
        acquire_campaign_lock(control)
        concurrency_checks.append({"phase": "campaign_start", "allowed_method_pids": [],
                                   "other_clients": guard_other_clients(control)})
        versions = verify_versions(control)
        if versions["postgresql_version"] != "17.11" or versions["postgresql_version_num"] != "170011" or versions["pgvector_version"] != "0.8.6":
            raise AssertionError(f"database version differs: {versions}")
        server_settings = validate_server_settings(control)
        write_json_exclusive(run_dir / "environment.json", {
            "host": host_environment(), "database_versions": versions,
            "server_controls": server_settings, "postgres_settings": postgres_settings(control),
        })
        first_identity = None
        for build in schedule["builds"]:
            build_number = build["build_number"]
            prefix = f"b{build_number}"
            last_phase = f"{prefix}_load"
            log.write(f"Build {build_number}: physically reloading 100k and building HNSW")
            concurrency_checks.append({"phase": last_phase, "allowed_method_pids": [],
                                       "other_clients": guard_other_clients(control)})
            phases = load_scale(control, base_ids=scale["selected_base_ids"], vectors=vectors,
                                buckets=scale["filter_buckets"], hnsw_build_settings=source_protocol["hnsw"])
            identity = capture_restart_identity(control)
            if first_identity is None:
                first_identity = identity
            else:
                assert_distinct_builds(first_identity, identity)
            write_json_exclusive(run_dir / f"{prefix}_identity.json", identity)
            evidence = database_evidence(control, scale_rows=SCALE_ROWS, thresholds=FILTERS)
            if evidence["ordered_vector_stream_sha256"] != source_checksum:
                raise AssertionError("loaded rows differ from canonical source")
            evidence.update({"source_vector_stream_sha256": source_checksum, "all_source_rows_equal": True})
            write_json_exclusive(run_dir / f"{prefix}_database_evidence.json", evidence)
            write_json_exclusive(run_dir / f"{prefix}_source_vector_samples.json", validate_source_samples(
                control, base_ids=scale["selected_base_ids"], vectors=vectors,
            ))
            last_phase = f"{prefix}_ground_truth"
            configure_session(control, "exact")
            gt_arguments = dict(run_id=run_id, scale_rows=SCALE_ROWS, thresholds=FILTERS,
                                qualifying_counts=counts, query_ids=queries["measured_query_ids"],
                                query_vectors=query_vectors, k=K, dataset_sha256=dataset["sha256"],
                                scale_manifest_sha256=scale_digest)
            truth_rows, phases["ground_truth_generation_ns"] = generate_ground_truth(control, **gt_arguments)
            write_jsonl_exclusive(run_dir / f"{prefix}_ground_truth.jsonl", truth_rows)
            repeated, phases["ground_truth_determinism_reexecution_ns"] = generate_ground_truth(control, **gt_arguments)
            if len(truth_rows) != 1000 or truth_rows != repeated:
                raise AssertionError("ground truth incomplete or deterministic reexecution differs")
            write_json_exclusive(run_dir / f"{prefix}_ground_truth_reexecution.json", {
                "passed": True, "reexecuted_records": len(repeated), "record_checksums_identical_in_order": True,
                "duration_ns": phases["ground_truth_determinism_reexecution_ns"],
            })
            truths = ground_truth_index(truth_rows)
            started = time.perf_counter_ns()
            validation = validate_ground_truth_numpy(
                records=truths, validation_keys=select_validation_keys(queries["measured_query_ids"], FILTERS, 20),
                base_ids=scale["selected_base_ids"], vectors=vectors, buckets=scale["filter_buckets"],
                query_vectors=query_vectors, k=K,
            )
            phases["independent_ground_truth_validation_ns"] = time.perf_counter_ns() - started
            write_json_exclusive(run_dir / f"{prefix}_ground_truth_validation.json", validation)
            write_json_exclusive(run_dir / f"{prefix}_phase_metrics.json", phases)
            for arm in build["arms"]:
                arm_prefix = f"{prefix}_{arm}"
                last_phase = f"{arm_prefix}_reset"
                log.write(f"{arm_prefix}: verified shared-buffer eviction; OS cache retained")
                concurrency_checks.append({"phase": last_phase, "allowed_method_pids": [],
                                           "other_clients": guard_other_clients(control)})
                before = capture_restart_identity(control)
                assert_same_arm_identity(identity, before)
                write_json_exclusive(run_dir / f"{arm_prefix}_identity_before.json", before)
                reset = evict_shared_buffers(control)
                reset.update({"reason": config["reset_policy"], "postmaster_restarted": False})
                write_json_exclusive(run_dir / f"{arm_prefix}_cache_reset.json", reset)
                connections, pids, settings = {}, {}, {}
                for method in METHODS:
                    connection = connect(application_name=f"preparation-{arm_prefix}-{method}")
                    opened.append(connection)
                    connections[method] = connection
                    pids[method], settings[method] = configure_session(connection, method)
                write_json_exclusive(run_dir / f"{arm_prefix}_method_sessions.json", {"backend_pids": pids, "settings": settings})
                last_phase = f"{arm_prefix}_plan_audit"
                plan_records, plan_ids = [], {}
                probe = queries["warmup_query_ids"][0]
                for method in METHODS:
                    for threshold in FILTERS:
                        plan_id, document, record = audit_plan(
                            connections[method], method=method, threshold=threshold,
                            query_id=probe, query_vector=query_vectors[probe], k=K, scale_rows=SCALE_ROWS,
                        )
                        record.update({"build_number": build_number, "arm": arm, "backend_pid": pids[method],
                                       "raw_plan_path": f"plans/{arm_prefix}_{plan_id}.json",
                                       "observed_session_settings": settings[method]})
                        write_json_exclusive(run_dir / record["raw_plan_path"], document)
                        plan_records.append(record)
                        plan_ids[(method, threshold)] = plan_id
                write_jsonl_exclusive(run_dir / f"{arm_prefix}_plan_assertions.jsonl", plan_records)
                if not all(record["passed"] for record in plan_records):
                    raise AssertionError("prepared query plan assertion failed")
                last_phase = f"{arm_prefix}_workload"
                snapshots = []
                for block in build["blocks"]:
                    method, threshold, block_index = block["method"], block["filter_threshold"], block["block_index"]
                    block_prefix = f"{arm_prefix}_block{block_index:02d}"
                    log.write(f"{block_prefix}: {method}, filter {threshold}")
                    passes = [("disjoint_warmup", 0, queries["warmup_query_ids"])]
                    if arm == "B":
                        passes.append(("measured_exposure", 0, block["exposure_query_order"]))
                    passes.extend(("measured", rep, ids) for rep, ids in enumerate(block["query_order_by_repetition"], 1))
                    with connections[method].cursor() as cursor:
                        for phase, repetition, ordered_queries in passes:
                            def produce():
                                nonlocal sequence_index
                                for query_id in ordered_queries:
                                    sequence_index += 1
                                    base = {"run_id": run_id, "config_sha256": digest, "build_number": build_number,
                                            "arm": arm, "block_index": block_index, "method": method,
                                            "filter_threshold": threshold, "query_id": query_id,
                                            "phase": phase, "repetition": repetition, "backend_pid": pids[method],
                                            "plan_audit_id": plan_ids[(method, threshold)]}
                                    row = observation(cursor=cursor, vector=query_vectors[query_id], base=base,
                                                      sequence_index=sequence_index, selected_buckets=selected_buckets,
                                                      truth=None if phase == "disjoint_warmup" else truths[(query_id, threshold)])
                                    yield row
                                    assert_valid_row(row)
                            suffix = f"timed_rep{repetition:02d}" if phase == "measured" else phase
                            journal.capture(f"chunk_{block_prefix}_{suffix}.jsonl", phase, produce())
                            snapshots.append({"block_index": block_index, "phase": phase, "repetition": repetition,
                                              "after_sequence_index": sequence_index, "host": host_environment()})
                final_prepared = prepared_statement_evidence(connections, len(FILTERS))
                write_json_exclusive(run_dir / f"{arm_prefix}_prepared_statements.json", final_prepared)
                assert_prepared_counts(final_prepared, arm)
                after_settings = capture_method_settings(connections)
                final_server_settings = validate_server_settings(control)
                write_json_exclusive(run_dir / f"{arm_prefix}_method_sessions_after.json", {
                    "backend_pids": pids, "settings": after_settings, "server_controls": final_server_settings,
                })
                assert_unchanged_settings(settings, after_settings)
                concurrency_checks.append({"phase": f"{arm_prefix}_end", "allowed_method_pids": sorted(pids.values()),
                                           "other_clients": guard_other_clients(control, pids.values())})
                for connection in connections.values():
                    connection.close()
                    opened.remove(connection)
                after = capture_restart_identity(control)
                assert_same_arm_identity(before, after)
                write_json_exclusive(run_dir / f"{arm_prefix}_identity_after.json", after)
                write_json_exclusive(run_dir / f"{arm_prefix}_resource_snapshots.json", snapshots)
        last_phase = "final_validation"
        executions = journal.consolidate({"measured"}, "executions.jsonl")
        preparation = journal.consolidate({"disjoint_warmup", "measured_exposure"}, "preparation.jsonl")
        if len(executions) != 60000 or len(preparation) != 7200:
            raise AssertionError("campaign observation counts differ from frozen protocol")
        all_rows = sorted(executions + preparation, key=lambda row: row["sequence_index"])
        if [row["sequence_index"] for row in all_rows] != list(range(1, 67201)):
            raise AssertionError("campaign observation sequence incomplete")
        for row in all_rows:
            assert_valid_row(row)
        write_json_exclusive(run_dir / "journal_manifest.json", {
            "chunks": journal.chunks, "hard_kill_loss_bound": "active pass",
            "caught_interruption_completed_rows_preserved": True,
            "query_timer_excludes_checkpoint_writes": True,
        })
        power_after = energy_mode()
        write_json_exclusive(run_dir / "power_after.json", power_after)
        verify_power_state(power_before, power_after)
        write_json_exclusive(run_dir / "concurrency_checks.json", {
            "advisory_lock_key": LOCK_KEY, "lock_held_until_campaign_end": True,
            "checks": concurrency_checks,
            "limitation": "boundary snapshots cannot exclude transient unobserved clients or non-database host activity",
        })
        if source_identity() != initial_source:
            raise AssertionError("experiment source bytes changed during campaign")
        write_json_exclusive(run_dir / "validation_report.json", {
            "passed": True, "run_id": run_id, "measured_executions": len(executions),
            "preparation_executions": len(preparation), "plan_audits": 60,
            "independent_ground_truth_checks": 40, "ground_truth_records": 2000,
            "source_unchanged": True, "elapsed_ns": time.perf_counter_ns() - campaign_start,
            "independent_offline_verification_required_before_interpretation": True,
        })
        for connection in opened:
            connection.close()
        opened.clear()
        log.write("Producer hard gates passed; finalizing. Independent offline verification remains required.")
        log.close()
        finalize_complete(run_dir, {"schema_version": 1, "run_id": run_id, "config_sha256": digest,
                                   "completed_at": datetime.now(timezone.utc).isoformat(), "valid": True,
                                   "measured_executions": 60000, "preparation_executions": 7200,
                                   "research_conclusion_authorized": False})
        return run_dir
    except BaseException as error:
        for connection in opened:
            try:
                connection.close()
            except BaseException:
                pass
        if not log._handle.closed:
            log.write(f"INVALID during {last_phase}: {type(error).__name__}: {error}")
        log.close()
        write_json_exclusive(run_dir / "failure.json", {"phase": last_phase, "error_type": type(error).__name__,
                                                       "error_message": str(error), "traceback": traceback.format_exc(),
                                                       "last_assigned_sequence_index": sequence_index,
                                                       "durable_completed_chunks": journal.chunks})
        finalize_invalid(run_dir, {"schema_version": 1, "run_id": run_id, "last_phase": last_phase,
                                  "failed_at": datetime.now(timezone.utc).isoformat(), "error_type": type(error).__name__})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_HDF5_PATH)
    arguments = parser.parse_args()
    print(run_campaign(arguments.config, arguments.dataset))


if __name__ == "__main__":
    main()
