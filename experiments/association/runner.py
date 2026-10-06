"""One immutable physical-graph stage of the frozen metadata/scale campaign."""
from __future__ import annotations
import argparse
import hashlib
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
import h5py
import numpy as np

from experiments.milestone2.artifacts import (
    finalize_complete, finalize_invalid, make_run_id, write_json_exclusive, write_jsonl_exclusive,
)
from experiments.milestone2.config import canonical_json_bytes, sha256_json
from experiments.milestone2.database import (
    connect, evict_shared_buffers, host_environment, postgres_settings, timed_execute_fetch, verify_versions,
)
from experiments.milestone2.dataset import (
    DEFAULT_HDF5_PATH, SOURCE_MANIFEST_PATH, build_scale_manifest, ensure_scale_order,
    load_query_vectors, load_scale_vectors, select_query_ids, serializable_scale_manifest,
    validate_hdf5, validate_source_manifest_identity,
)
from experiments.milestone2.ground_truth import (
    ground_truth_index, select_validation_keys, validate_ground_truth_numpy,
)
from experiments.milestone2.metrics import canonical_recall_at_k, tie_aware_recall_at_k, validate_returned_results
from experiments.milestone2.runner import RunLog, energy_mode, git_state, require_clean_git_state, verify_power_state
from experiments.preparation.journal import CheckpointJournal
from experiments.preparation.runner import (
    LOCK_KEY, acquire_campaign_lock, guard_other_clients, source_identity, assert_distinct_builds,
    assert_valid_row, capture_method_settings, assert_unchanged_settings,
)
from . import database as db
from .metadata import build_metadata, neighborhoods, association_diagnostics
from .protocol import (
    ROOT, PROTOCOL, STAGES, METHODS, MODES, FILTERS, K, stage_config, config_digest,
    schedule, configure_session, validate_server_settings,
)

def read_json(path):
    return json.loads(Path(path).read_text())

def prepared_evidence(connections, mode):
    if set(connections) != set(METHODS):
        raise AssertionError("all three persistent method sessions are required")
    evidence = {}
    for method, connection in connections.items():
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, statement, parameter_types::text, generic_plans, custom_plans "
                           "FROM pg_prepared_statements ORDER BY name", prepare=False)
            rows = [dict(zip(("name", "statement", "parameter_types", "generic_plans", "custom_plans"), r))
                    for r in cursor.fetchall() if "association.sift_" in r[1]]
        expected = {db.search_sql(method, mode, t).replace("%s", "$1") for t in FILTERS}
        if len(rows) != 5 or {r["statement"] for r in rows} != expected or any(
            r["parameter_types"] != "{vector}" or r["generic_plans"] != 1022 or r["custom_plans"] != 0
            for r in rows
        ):
            raise AssertionError("mode-specific prepared statement count/SQL mismatch")
        evidence[method] = rows
    return evidence

def observation(cursor, vector, base, sequence, buckets, truth):
    sql = db.search_sql(base["method"], base["metadata_mode"], base["filter_threshold"])
    started = time.perf_counter_ns()
    timed = timed_execute_fetch(cursor, sql, (vector,))
    ids, distances = [r[0] for r in timed.rows], [r[1] for r in timed.rows]
    scores = validate_returned_results(ids, distances, k=K, selected_buckets=buckets,
                                      threshold=base["filter_threshold"])
    canonical = tie = None
    if truth is not None and timed.error_type is None:
        canonical = canonical_recall_at_k(ids, truth["canonical_ids"], K)
        tie = tie_aware_recall_at_k(ids, truth["strictly_closer_ids"], truth["boundary_tie_ids"], K)
    return {**base, "schema_version": 1, "sequence_index": sequence, "start_monotonic_ns": started,
            "duration_ns": timed.duration_ns, "k": K, "prepared": True,
            "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            "result_ids": ids, "distances": distances, **scores,
            "canonical_recall_at_10": canonical, "tie_aware_recall_at_10": tie,
            "ground_truth_record_sha256": None if truth is None else truth["record_sha256"],
            "error_type": timed.error_type, "error_message": timed.error_message,
            "timeout": timed.error_type == "QueryCanceled"}

def resource_gate(config, host):
    if host["memory_available_bytes"] < config["resource_min_available_bytes"]:
        raise RuntimeError("available memory below frozen resource gate")
    if host["disk_free_bytes"] < config["resource_min_disk_bytes"]:
        raise RuntimeError("available disk below frozen resource gate")

def check_predecessor(config, previous, initial_source):
    position = STAGES.index((config["scale_rows"], config["build_number"]))
    if position == 0:
        if previous is not None:
            raise ValueError("first stage must not specify a predecessor")
        return None
    if previous is None:
        raise ValueError("next stage requires independently verified predecessor")
    from .verify import verify_run
    proof = verify_run(Path(previous))
    old_config = read_json(Path(previous) / "config.json")
    if (old_config["scale_rows"], old_config["build_number"]) != STAGES[position-1]:
        raise ValueError("predecessor is not the previous frozen stage")
    manifest = read_json(Path(previous) / "manifest.json")
    if manifest["source_file_sha256"] != initial_source:
        raise ValueError("experiment implementation changed between matched stages")
    return {"run_directory": str(Path(previous).resolve()), "verification": proof}

def run_stage(scale, build, *, dataset_path=DEFAULT_HDF5_PATH, previous=None):
    config = stage_config(scale, build)
    if canonical_json_bytes(read_json(ROOT / "config/metadata-association-v1.json")) != canonical_json_bytes(PROTOCOL):
        raise ValueError("checked-in protocol differs from frozen implementation")
    initial_git = git_state()
    require_clean_git_state(initial_git)
    initial_source = source_identity()
    predecessor = check_predecessor(config, previous, initial_source)
    digest = config_digest(config)
    run_dir = ROOT / "raw_results/association" / make_run_id(digest)
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "plans").mkdir()
    (run_dir / "ACTIVE").touch(exist_ok=False)
    journal, log = CheckpointJournal(run_dir), RunLog(run_dir / "run.log")
    opened, checks, snapshots = [], [], []
    phase, sequence = "initialization", 0
    started = time.perf_counter_ns()
    try:
        log.write(f"Starting association stage: scale={scale}, build={build}, same-graph metadata modes")
        source_protocol = read_json(ROOT / config["source_protocol"])
        write_json_exclusive(run_dir / "config.json", config)
        write_json_exclusive(run_dir / "manifest.json", {
            "schema_version": 1, "run_id": run_dir.name, "config_sha256": digest,
            "git_at_start": initial_git, "expected_source_commit": initial_git["commit"],
            "source_file_sha256": initial_source, "source_protocol": source_protocol,
            "started_at": datetime.now(timezone.utc).isoformat(), "predecessor": predecessor,
            "research_conclusion_authorized": False,
        })
        power = energy_mode()
        write_json_exclusive(run_dir / "power_before.json", power)
        if not power["ac_power_detected"]:
            raise RuntimeError("AC power required")
        resource_gate(config, host_environment())
        phase = "source_validation"
        canonical = read_json(SOURCE_MANIFEST_PATH)
        source_validation = validate_source_manifest_identity(canonical, source_protocol["dataset"])
        dataset = validate_hdf5(dataset_path, expected_sha256=source_protocol["dataset"]["expected_sha256"])
        if dataset["byte_size"] != source_protocol["dataset"]["expected_bytes"]:
            raise AssertionError("source size mismatch")
        dataset.update(canonical_source=canonical, source_manifest_identity_validation=source_validation)
        write_json_exclusive(run_dir / "dataset_manifest.json", dataset)
        assignment = source_protocol["scale_assignment"]
        order, order_manifest = ensure_scale_order(
            expected_ordered_ids_sha256=assignment["expected_ordered_ids_sha256"],
            expected_cache_sha256=assignment["expected_cache_sha256"])
        scale_data = build_scale_manifest(order, scale, FILTERS)
        write_json_exclusive(run_dir / "scale_manifest.json", {
            **serializable_scale_manifest(scale_data), "global_order": order_manifest})
        base_ids, legacy = scale_data["selected_base_ids"], scale_data["filter_buckets"]
        vectors = load_scale_vectors(dataset_path, base_ids)
        with h5py.File(dataset_path, "r") as handle:
            anchor = np.asarray(handle["train"][0], dtype=np.float32)
        radial, metadata = build_metadata(base_ids, vectors, anchor)
        metadata_digest = sha256_json(metadata)
        write_json_exclusive(run_dir / "metadata_manifest.json", metadata)
        queries = select_query_ids()
        qvectors = load_query_vectors(dataset_path, queries["measured_query_ids"] + queries["warmup_query_ids"])
        queries["vector_sha256"] = {str(q): hashlib.sha256(np.asarray(v, dtype="<f4").tobytes()).hexdigest()
                                    for q, v in qvectors.items()}
        write_json_exclusive(run_dir / "queries.json", queries)
        execution_schedule = schedule(config, queries["measured_query_ids"])
        write_json_exclusive(run_dir / "schedule.json", execution_schedule)
        phase = "association_qualification"
        log.write("Computing source-exact neighborhoods and prespecified association manipulation check")
        diagnostic_start = time.perf_counter_ns()
        neighbors = neighborhoods(base_ids, vectors, qvectors, legacy, radial, anchor=anchor)
        write_jsonl_exclusive(run_dir / "neighbors.jsonl", neighbors)
        diagnostics = association_diagnostics(neighbors, base_ids, radial, queries["measured_query_ids"],
                                             seed=config["association_seed"],
                                             permutations=config["association_permutations"])
        write_json_exclusive(run_dir / "association_diagnostics.json", diagnostics)
        if not diagnostics["gate_passed"]:
            raise AssertionError("prespecified metadata association manipulation check failed; do not retune")
        diagnostic_ns = time.perf_counter_ns() - diagnostic_start
        log.write("Association manipulation check passed; physically loading vectors and both metadata columns")
        phase = "database_load"
        resource_gate(config, host_environment())
        control = connect(application_name="association-control")
        opened.append(control)
        acquire_campaign_lock(control)
        checks.append({"phase": "stage_start", "allowed_method_pids": [], "other_clients": guard_other_clients(control)})
        versions = verify_versions(control)
        if versions["postgresql_version"] != "17.11" or versions["pgvector_version"] != "0.8.6":
            raise AssertionError("database versions differ from frozen profile")
        server_settings = validate_server_settings(control)
        write_json_exclusive(run_dir / "environment.json", {
            "host": host_environment(), "database_versions": versions,
            "server_controls": server_settings, "postgres_settings": postgres_settings(control)})
        checks.append({"phase": "load", "allowed_method_pids": [], "other_clients": guard_other_clients(control)})
        phases = db.load_scale(control, base_ids=base_ids, vectors=vectors, legacy=legacy, radial=radial)
        phases["metadata_diagnostics_ns"] = diagnostic_ns
        evidence = db.evidence(control, base_ids=base_ids, vectors=vectors, legacy=legacy, radial=radial)
        physical = db.identity(control)
        if predecessor is not None:
            assert_distinct_builds(read_json(Path(previous) / "identity.json"), physical)
        write_json_exclusive(run_dir / "database_evidence.json", evidence)
        write_json_exclusive(run_dir / "identity.json", physical)
        all_truths = {}
        configure_session(control, "exact")
        phase = "ground_truth"
        for mode, labels in (("legacy", legacy), ("radial", radial)):
            arguments = dict(mode=mode, run_id=run_dir.name, scale_rows=scale, thresholds=FILTERS,
                             query_ids=queries["measured_query_ids"], query_vectors=qvectors,
                             dataset_sha256=dataset["sha256"], metadata_sha256=metadata_digest)
            records, ns = db.generate_truth(control, **arguments)
            phases[f"{mode}_ground_truth_ns"] = ns
            write_jsonl_exclusive(run_dir / f"{mode}_ground_truth.jsonl", records)
            repeated, ns = db.generate_truth(control, **arguments)
            if len(records) != 1000 or records != repeated:
                raise AssertionError("mode-specific truth grid/reexecution differs")
            phases[f"{mode}_truth_reexecution_ns"] = ns
            write_json_exclusive(run_dir / f"{mode}_truth_reexecution.json", {
                "passed": True, "metadata_mode": mode, "reexecuted_records": 1000,
                "record_checksums_identical_in_order": True, "duration_ns": ns})
            truths = ground_truth_index(records)
            all_truths[mode] = truths
            began = time.perf_counter_ns()
            validation = validate_ground_truth_numpy(
                records=truths, validation_keys=select_validation_keys(queries["measured_query_ids"], FILTERS, 20),
                base_ids=base_ids, vectors=vectors, buckets=labels, query_vectors=qvectors, k=K)
            phases[f"{mode}_numpy_validation_ns"] = time.perf_counter_ns()-began
            write_json_exclusive(run_dir / f"{mode}_truth_validation.json", validation)
        write_json_exclusive(run_dir / "phase_metrics.json", phases)
        for mode in execution_schedule["modes"]:
            phase = f"{mode}_reset"
            log.write(f"{mode}: verified buffer eviction, persistent sessions and actual prepared-plan audits")
            checks.append({"phase": phase, "allowed_method_pids": [], "other_clients": guard_other_clients(control)})
            before = db.identity(control)
            if before != physical:
                raise AssertionError("physical graph changed before mode")
            write_json_exclusive(run_dir / f"{mode}_identity_before.json", before)
            reset = evict_shared_buffers(control)
            reset.update(postmaster_restarted=False, reason=config["reset"])
            write_json_exclusive(run_dir / f"{mode}_cache_reset.json", reset)
            connections, pids, settings = {}, {}, {}
            for method in METHODS:
                connection = connect(application_name=f"association-{mode}-{method}")
                opened.append(connection)
                connections[method] = connection
                pids[method], settings[method] = configure_session(connection, method)
            write_json_exclusive(run_dir / f"{mode}_method_sessions.json", {"backend_pids": pids, "settings": settings})
            plan_records, plan_ids = [], {}
            probe = queries["warmup_query_ids"][0]
            for method in METHODS:
                for threshold in FILTERS:
                    pid, document, record = db.audit_plan(
                        connections[method], method=method, mode=mode, threshold=threshold,
                        query_id=probe, query_vector=qvectors[probe], scale_rows=scale)
                    record.update(metadata_mode=mode, build_number=build, backend_pid=pids[method],
                                  observed_session_settings=settings[method], raw_plan_path=f"plans/{mode}_{pid}.json")
                    write_json_exclusive(run_dir / record["raw_plan_path"], document)
                    plan_records.append(record); plan_ids[method, threshold] = pid
            write_jsonl_exclusive(run_dir / f"{mode}_plan_assertions.jsonl", plan_records)
            if len(plan_records) != 15 or not all(r["passed"] for r in plan_records):
                raise AssertionError("mode-specific prepared plans failed")
            labels = legacy if mode == "legacy" else radial
            buckets = {int(i): int(b) for i, b in zip(base_ids, labels, strict=True)}
            phase = f"{mode}_measurement"
            for block in execution_schedule["blocks"]:
                method, threshold = block["method"], block["filter_threshold"]
                log.write(f"{mode} block{block['block_index']:02}: {method}, filter {threshold}")
                passes = [("disjoint_warmup", 0, queries["warmup_query_ids"])]
                passes += [("measured", r, ids) for r, ids in enumerate(block["query_order_by_repetition"], 1)]
                with connections[method].cursor() as cursor:
                    for pass_phase, repetition, query_ids in passes:
                        def produce():
                            nonlocal sequence
                            for q in query_ids:
                                sequence += 1
                                base = {"run_id": run_dir.name, "config_sha256": digest, "build_number": build,
                                        "scale_rows": scale, "metadata_mode": mode, "method": method,
                                        "filter_threshold": threshold, "query_id": q,
                                        "block_index": block["block_index"], "repetition": repetition,
                                        "phase": pass_phase, "backend_pid": pids[method],
                                        "plan_audit_id": plan_ids[method, threshold]}
                                row = observation(cursor, qvectors[q], base, sequence, buckets,
                                                  None if pass_phase == "disjoint_warmup" else all_truths[mode][q, threshold])
                                yield row
                                assert_valid_row(row)
                        suffix = f"rep{repetition:02}" if pass_phase == "measured" else "warmup"
                        journal.capture(f"chunk_{mode}_block{block['block_index']:02}_{suffix}.jsonl", pass_phase, produce())
                        snapshots.append({"metadata_mode": mode, "block_index": block["block_index"],
                                          "phase": pass_phase, "repetition": repetition,
                                          "after_sequence_index": sequence, "host": host_environment()})
            write_json_exclusive(run_dir / f"{mode}_prepared_statements.json", prepared_evidence(connections, mode))
            after_settings = capture_method_settings(connections)
            assert_unchanged_settings(settings, after_settings)
            write_json_exclusive(run_dir / f"{mode}_method_sessions_after.json", {
                "backend_pids": pids, "settings": after_settings, "server_controls": validate_server_settings(control)})
            checks.append({"phase": f"{mode}_end", "allowed_method_pids": sorted(pids.values()),
                           "other_clients": guard_other_clients(control, pids.values())})
            for connection in connections.values():
                connection.close(); opened.remove(connection)
            after = db.identity(control)
            if before != after:
                raise AssertionError("physical graph or server changed within metadata mode")
            write_json_exclusive(run_dir / f"{mode}_identity_after.json", after)
        phase = "final_validation"
        measured = journal.consolidate({"measured"}, "executions.jsonl")
        warmups = journal.consolidate({"disjoint_warmup"}, "preparation.jsonl")
        if len(measured) != 30000 or len(warmups) != 600:
            raise AssertionError("incomplete execution grid")
        if sorted(r["sequence_index"] for r in measured+warmups) != list(range(1, 30601)):
            raise AssertionError("duplicate or missing chronological observation")
        for row in measured+warmups:
            assert_valid_row(row)
        write_json_exclusive(run_dir / "journal_manifest.json", {
            "chunks": journal.chunks, "hard_kill_loss_bound": "active pass",
            "caught_interruption_completed_rows_preserved": True, "query_timer_excludes_checkpoint_writes": True})
        write_json_exclusive(run_dir / "resource_snapshots.json", snapshots)
        after_power = energy_mode()
        write_json_exclusive(run_dir / "power_after.json", after_power)
        verify_power_state(power, after_power)
        write_json_exclusive(run_dir / "concurrency_checks.json", {
            "advisory_lock_key": LOCK_KEY, "lock_held_until_stage_end": True, "checks": checks,
            "limitation": "boundary checks cannot exclude transient clients or background host activity"})
        if source_identity() != initial_source:
            raise AssertionError("experiment source changed during stage")
        write_json_exclusive(run_dir / "validation_report.json", {
            "passed": True, "run_id": run_dir.name, "measured_executions": 30000,
            "preparation_executions": 600, "plan_audits": 30, "ground_truth_records": 2000,
            "independent_ground_truth_checks": 40, "source_unchanged": True,
            "elapsed_ns": time.perf_counter_ns()-started,
            "independent_offline_verification_required_before_interpretation": True})
        for connection in opened:
            connection.close()
        opened.clear()
        log.write("Producer gates passed; independent offline verification required before next stage")
        log.close()
        finalize_complete(run_dir, {"schema_version": 1, "run_id": run_dir.name, "config_sha256": digest,
                                   "valid": True, "completed_at": datetime.now(timezone.utc).isoformat(),
                                   "measured_executions": 30000, "preparation_executions": 600,
                                   "research_conclusion_authorized": False})
        return run_dir
    except BaseException as error:
        for connection in opened:
            try:
                connection.close()
            except BaseException:
                pass
        if not log._handle.closed:
            log.write(f"INVALID during {phase}: {type(error).__name__}: {error}")
        log.close()
        write_json_exclusive(run_dir / "failure.json", {
            "phase": phase, "error_type": type(error).__name__, "error_message": str(error),
            "traceback": traceback.format_exc(), "last_assigned_sequence_index": sequence,
            "durable_completed_chunks": journal.chunks})
        finalize_invalid(run_dir, {"schema_version": 1, "run_id": run_dir.name, "last_phase": phase,
                                   "error_type": type(error).__name__, "failed_at": datetime.now(timezone.utc).isoformat()})
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=int, required=True)
    parser.add_argument("--build", type=int, required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_HDF5_PATH)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    print(run_stage(args.scale, args.build, dataset_path=args.dataset, previous=args.previous))
