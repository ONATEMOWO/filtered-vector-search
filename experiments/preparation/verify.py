"""Read-only validation of preparation-policy evidence, not a live database test.

Result metrics, artifact coverage and schedules are checked independently. Source
selection, PostgreSQL plan assertions and sampled NumPy truth validation reuse
the existing audited helpers; this is not wholly independent implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from experiments.milestone2.artifacts import sha256_file
from experiments.milestone2.config import sha256_json
from experiments.milestone2.database import search_sql, source_stream_checksum
from experiments.milestone2.dataset import (
    build_scale_manifest, deterministic_id_order, load_query_vectors,
    load_scale_vectors, select_query_ids, validate_hdf5,
    validate_source_manifest_identity,
)
from experiments.milestone2.ground_truth import (
    ground_truth_index, make_ground_truth_record, select_validation_keys,
    validate_ground_truth_numpy,
)
from experiments.milestone2.plans import verify_plan_document
from experiments.preparation.protocol import (
    PROTOCOL_PATH, SERVER_CONTROLS, SESSION_CONTROLS, build_schedule, load_protocol,
)

ROOT = Path(__file__).resolve().parents[2]
METHODS = ("exact", "hnsw_standard", "hnsw_iterative")
FILTERS = (50, 20, 10, 5, 1)
RELATIONS = {
    "sift_exact": "r", "sift_hnsw": "r", "sift_exact_pkey": "i",
    "sift_hnsw_pkey": "i", "sift_exact_filter_bucket_idx": "i",
    "sift_hnsw_embedding_idx": "i",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def verify_manifest(run_dir: Path, *, complete: bool = True) -> dict[str, str]:
    """Reject omitted, extra, duplicate, traversing or symlinked payload paths."""
    require(not (run_dir / "INVALID.json").exists(), "invalid run is not successful evidence")
    require(not (run_dir / "failure.json").exists(), "failure artifact in completed evidence")
    if complete:
        require((run_dir / "COMPLETE.json").is_file(), "missing COMPLETE marker")
        require(not (run_dir / "ACTIVE").exists(), "completed run is ACTIVE")
    payload: dict[str, str] = {}
    for line in (run_dir / "checksums.sha256").read_text().splitlines():
        require(bool(re.fullmatch(r"[0-9a-f]{64}  .+", line)), "malformed checksum line")
        digest, name = line.split("  ", 1)
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe checksum path")
        require(name not in payload, "duplicate checksum path")
        require(name not in {"ACTIVE", "COMPLETE.json", "checksums.sha256", "INVALID.json"},
                "terminal marker or manifest included as payload")
        payload[name] = digest
    actual = set()
    for path in run_dir.rglob("*"):
        require(not path.is_symlink(), "symlink inside evidence bundle")
        if path.is_file() and path.name not in {"ACTIVE", "COMPLETE.json", "checksums.sha256"}:
            actual.add(path.relative_to(run_dir).as_posix())
    require(actual == set(payload), "payload manifest coverage differs from files")
    for name, expected in payload.items():
        require(sha256_file(run_dir / name) == expected, f"checksum mismatch: {name}")
    return payload


def validate_results(row: dict[str, Any], buckets: dict[int, int], truth: dict[str, Any] | None) -> None:
    """Independent fixed-denominator canonical and boundary-tie recall formulas."""
    ids, distances = row["result_ids"], row["distances"]
    require(isinstance(ids, list) and isinstance(distances, list), "result fields must be lists")
    require(len(ids) == len(distances) <= 10, "invalid result lengths")
    require(all(type(value) is int for value in ids) and len(set(ids)) == len(ids), "invalid or duplicate IDs")
    require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in distances),
            "invalid distances")
    require(all(a <= b for a, b in zip(distances, distances[1:])), "unordered distances")
    require(all(identifier in buckets and buckets[identifier] < row["filter_threshold"] for identifier in ids),
            "result outside scale or filter")
    expected = {"returned_count": len(ids), "returned_k": len(ids) == 10,
                "shortfall": 10 - len(ids), "ids_unique": True, "scale_valid": True,
                "filter_valid": True, "distance_order_valid": True}
    for name, value in expected.items():
        require(row.get(name) == value and type(row.get(name)) is type(value), f"incorrect {name}")
    if truth is None:
        require(row.get("canonical_recall_at_10") is None and row.get("tie_aware_recall_at_10") is None,
                "disjoint warm-up recall must be null")
        require(row.get("ground_truth_record_sha256") is None, "disjoint warm-up has truth reference")
        return
    found = set(ids)
    canonical = len(found & set(truth["canonical_ids"])) / 10
    closer = set(truth["strictly_closer_ids"])
    tied = (len(found & closer) + min(len(found & set(truth["boundary_tie_ids"])), 10 - len(closer))) / 10
    for name, expected_recall in (("canonical_recall_at_10", canonical), ("tie_aware_recall_at_10", tied)):
        value = row.get(name)
        require(type(value) in (int, float) and math.isfinite(value) and
                math.isclose(value, expected_recall, rel_tol=0, abs_tol=1e-15), f"incorrect {name}")
    require(row.get("ground_truth_record_sha256") == truth["record_sha256"], "wrong ground-truth reference")
    if row["method"] == "exact":
        require(ids == truth["canonical_ids"] and canonical == 1 and tied == 1, "exact result differs from truth")


def validate_identity(identity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = identity.get("relations", [])
    found = {row.get("relation"): row for row in rows}
    require(len(rows) == len(RELATIONS) and {name: row.get("kind") for name, row in found.items()} == RELATIONS,
            "physical relation matrix differs")
    for field in ("oid", "filenode"):
        values = [row.get(field) for row in rows]
        require(all(type(value) is int and value > 0 for value in values) and len(set(values)) == len(rows),
                f"invalid physical {field}")
    require(identity.get("server_version_num") == "170011" and bool(identity.get("system_identifier"))
            and bool(identity.get("database")), "missing or wrong cluster/version identity")
    return found


def verify_prepared(prepared: dict[str, Any], arm: str) -> None:
    require(arm in ("A", "B"), "unknown preparation arm")
    require(set(prepared) == set(METHODS), "prepared method matrix differs")
    for method in METHODS:
        statements = prepared[method]
        expected = {search_sql(method, threshold, 10).replace("%s", "$1") for threshold in FILTERS}
        require(len(statements) == 5 and {row["statement"] for row in statements} == expected,
                "prepared SQL matrix differs")
        require(len({row["name"] for row in statements}) == 5, "duplicate prepared names")
        for row in statements:
            require(row.get("parameter_types") == "{vector}" and row.get("custom_plans") == 0 and
                    type(row.get("custom_plans")) is int and
                    row.get("generic_plans") == (1022 if arm == "A" else 1222) and
                    type(row.get("generic_plans")) is int, "incorrect prepared execution counts or parameter types")


def verify_schedule_rows(
    executions: list[dict[str, Any]], preparation: list[dict[str, Any]],
    schedule: dict[str, Any], measured_ids: list[int], warmup_ids: list[int],
) -> None:
    """Check exact chronological order, not just membership or row counts."""
    expected = []
    for build in schedule["builds"]:
        number = build["build_number"]
        require(number in (1, 2), "unknown scheduled build")
        require(build["arms"] == (["A", "B"] if number == 1 else ["B", "A"]), "incorrect arm order")
        for arm in build["arms"]:
            for block in build["blocks"]:
                common = (number, arm, block["block_index"], block["method"], block["filter_threshold"])
                expected.extend((*common, "disjoint_warmup", 0, query) for query in warmup_ids)
                if arm == "B":
                    require(sorted(block["exposure_query_order"]) == sorted(measured_ids), "invalid exposure permutation")
                    expected.extend((*common, "measured_exposure", 0, query) for query in block["exposure_query_order"])
                require(len(block["query_order_by_repetition"]) == 5, "incomplete repetition schedule")
                for repetition, order in enumerate(block["query_order_by_repetition"], 1):
                    require(sorted(order) == sorted(measured_ids), "invalid measured permutation")
                    expected.extend((*common, "measured", repetition, query) for query in order)
    for rows, allowed in ((executions, {"measured"}), (preparation, {"disjoint_warmup", "measured_exposure"})):
        require(all(row.get("phase") in allowed for row in rows), "row in wrong phase file")
        require(all(type(row.get("sequence_index")) is int for row in rows), "invalid sequence index")
        require([row["sequence_index"] for row in rows] == sorted(row["sequence_index"] for row in rows),
                "consolidation not chronological")
    rows = sorted(executions + preparation, key=lambda row: row["sequence_index"])
    require([row["sequence_index"] for row in rows] == list(range(1, len(expected) + 1)),
            "missing or duplicated chronological execution")
    fields = ("build_number", "arm", "block_index", "method", "filter_threshold", "phase", "repetition", "query_id")
    observed = [tuple(row.get(name) for name in fields) for row in rows]
    require(observed == expected, "execution order differs from deterministic schedule")


def verify_chunks(run_dir: Path, journal: dict[str, Any], executions: list, preparation: list) -> None:
    chunks = journal["chunks"]
    seen: set[str] = set()
    measured, prepared = [], []
    previous_last = 0
    for chunk in chunks:
        name = chunk["file"]
        path = Path(name)
        require(name not in seen and path.name == name and name.startswith("chunk_")
                and name.endswith(".jsonl") and ".partial." not in name, "unsafe or duplicate journal chunk")
        seen.add(name)
        rows = read_jsonl(run_dir / path)
        require(bool(rows) and chunk["row_count"] == len(rows), "journal chunk count differs")
        require(chunk["sha256"] == sha256_file(run_dir / path), "journal chunk checksum differs")
        require(chunk["first_sequence_index"] == rows[0]["sequence_index"] and
                chunk["last_sequence_index"] == rows[-1]["sequence_index"], "journal sequence range differs")
        require(chunk["first_sequence_index"] == previous_last + 1, "journal chunks are not chronologically contiguous")
        previous_last = chunk["last_sequence_index"]
        require(all(row["phase"] == chunk["phase"] for row in rows), "journal chunk mixes phases")
        require(chunk["phase"] in ("measured", "disjoint_warmup", "measured_exposure"), "unknown journal phase")
        (measured if chunk["phase"] == "measured" else prepared).extend(rows)
    actual = {path.name for path in run_dir.glob("chunk_*.jsonl")}
    require(actual == seen, "journal chunk coverage differs")
    require(measured == executions and prepared == preparation, "consolidations differ from durable chunks")


def verify_row_provenance(row: dict[str, Any], run_id: str, digest: str, pid: int, plan_id: str) -> None:
    expected = {"run_id": run_id, "config_sha256": digest, "scale_rows": 100000,
                "k": 10, "prepared": True, "backend_pid": pid, "plan_audit_id": plan_id,
                "sql_sha256": hashlib.sha256(search_sql(row["method"], row["filter_threshold"], 10).encode()).hexdigest()}
    require(all(row.get(name) == value for name, value in expected.items()), "row provenance differs")
    require(row.get("prepared") is True and all(type(row.get(name)) is int for name in
            ("scale_rows", "k", "backend_pid")), "row provenance has incorrect value types")
    require(row.get("error_type") is None and row.get("error_message") is None and row.get("timeout") is False,
            "failed execution in completed run")
    require(type(row.get("duration_ns")) is int and row["duration_ns"] > 0 and
            type(row.get("start_monotonic_ns")) is int and row["start_monotonic_ns"] > 0,
            "invalid execution timing")


def verify_distances(row: dict[str, Any], vectors: np.ndarray, positions: dict[int, int], query: np.ndarray) -> None:
    if not row["result_ids"]:
        return
    selected = np.asarray(vectors[[positions[value] for value in row["result_ids"]]], dtype=np.float64)
    distances = np.sqrt(np.sum((selected - np.asarray(query, dtype=np.float64)) ** 2, axis=1))
    require(np.allclose(distances, row["distances"], rtol=2e-6, atol=2e-5), "L2 distances differ from source")


def verify_truth(
    records: list[dict[str, Any]], *, run_id: str, dataset_sha: str, scale_sha: str,
    selected: dict[str, Any], query_ids: list[int], vectors: np.ndarray, queries: dict,
    reexecution: dict, independent: dict,
) -> dict:
    truth = ground_truth_index(records)
    require(set(truth) == {(query, threshold) for query in query_ids for threshold in FILTERS}, "incomplete truth grid")
    buckets = dict(zip(map(int, selected["selected_base_ids"]), map(int, selected["filter_buckets"]), strict=True))
    for (query, threshold), record in truth.items():
        identifiers, distances = record["all_with_ties_ids"], record["all_with_ties_distances"]
        require(len(identifiers) == len(distances) and len(identifiers) == len(set(identifiers)), "invalid truth rows")
        require(all(type(value) is int and value in buckets and buckets[value] < threshold for value in identifiers),
                "truth row outside filter")
        require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in distances),
                "invalid truth distances")
        rebuilt = make_ground_truth_record(
            run_id=run_id, scale_rows=100000, threshold=threshold, qualifying_count=1000 * threshold,
            query_id=query, k=10, rows=zip(identifiers, distances, strict=True),
            dataset_sha256=dataset_sha, scale_manifest_sha256=scale_sha,
        )
        require(rebuilt == record and max(distances) == record["boundary_distance"], "truth provenance/ranking/ties differ")
    require(reexecution.get("passed") is True and reexecution.get("record_checksums_identical_in_order") is True
            and reexecution.get("reexecuted_records") == 1000, "truth reexecution failed or incomplete")
    recalculated = validate_ground_truth_numpy(
        records=truth, validation_keys=select_validation_keys(query_ids, FILTERS, 20),
        base_ids=selected["selected_base_ids"], vectors=vectors, buckets=selected["filter_buckets"],
        query_vectors=queries, k=10,
    )
    require(independent == recalculated, "sampled NumPy truth evidence does not reproduce")
    return truth


def verify_database(database: dict, selected: dict, source_digest: str) -> None:
    expected = {
        "exact_count": 100000, "hnsw_count": 100000, "unequal_row_count": 0,
        "dimensions": {"minimum": 128, "maximum": 128},
        "source_vector_stream_sha256": source_digest, "ordered_vector_stream_sha256": source_digest,
        "all_source_rows_equal": True,
        "rank_contract": {"distinct_ranks": 100000, "minimum": 0, "maximum": 99999, "bucket_mismatches": 0},
        "filter_counts": {str(t): {"exact": t * 1000, "hnsw": t * 1000, "expected": t * 1000} for t in FILTERS},
    }
    require(all(database.get(name) == value for name, value in expected.items()), "physical data/source/filter evidence differs")
    nonfinite = database.get("nonfinite_vector_counts", {})
    require(nonfinite.get("exact") == 0 and nonfinite.get("hnsw") == 0, "nonfinite vectors in physical tables")
    indexes = database["indexes"]
    require(not any(row["table"] == "sift_exact" and "(embedding" in row["definition"] for row in indexes),
            "exact table has a vector index")
    require(not any(row["table"] == "sift_hnsw" and "(filter_bucket)" in row["definition"] for row in indexes),
            "HNSW table has metadata index")
    require(sum(row["table"] == "sift_exact" and "USING btree (filter_bucket)" in row["definition"] for row in indexes) == 1,
            "missing exact metadata index")
    require(sum(row["index"] == "sift_hnsw_embedding_idx" and "USING hnsw (embedding vector_l2_ops)" in row["definition"]
                and "m='16'" in row["definition"] and "ef_construction='64'" in row["definition"] for row in indexes) == 1,
            "missing or misconfigured HNSW graph")
    sizes = database["relation_sizes"]
    require(len(sizes) == 6 and {row["relation"]: row["kind"] for row in sizes} == RELATIONS and
            all(type(row["relation_bytes"]) is int and row["relation_bytes"] > 0 for row in sizes), "invalid relation sizes")


def verify_arm(run_dir: Path, build: int, arm: str, identity: dict, warmup_query: int) -> tuple[dict, dict]:
    prefix = f"b{build}_{arm}_"
    before = read_json(run_dir / f"{prefix}identity_before.json")
    after = read_json(run_dir / f"{prefix}identity_after.json")
    validate_identity(before)
    validate_identity(after)
    require(identity == before == after, "physical graph, cluster or postmaster changed within a build")
    cache = read_json(run_dir / f"{prefix}cache_reset.json")
    require(cache.get("operating_system_cache_flushed") is False and cache.get("postmaster_restarted") is False,
            "cache reset misrepresents OS flush or restart")
    require(cache.get("method") == "pg_buffercache_evict over a materialized buffer-id snapshot after CHECKPOINT"
            and cache.get("after", {}).get("buffers_used") == 0,
            "shared buffer eviction did not succeed")
    sessions = read_json(run_dir / f"{prefix}method_sessions.json")
    pids, settings = sessions["backend_pids"], sessions["settings"]
    require(set(pids) == set(METHODS) and set(settings) == set(METHODS) and len(set(pids.values())) == 3 and
            all(type(pid) is int and pid > 0 for pid in pids.values()), "invalid persistent method sessions")
    for method, observed in settings.items():
        expected = {**SESSION_CONTROLS, "work_mem": "4MB" if method == "exact" else "64MB",
                    "jit": "off", "plan_cache_mode": "force_generic_plan", "statement_timeout": "2min"}
        require(all(observed.get(name) == value for name, value in expected.items()), "session controls differ")
    after_sessions = read_json(run_dir / f"{prefix}method_sessions_after.json")
    require(after_sessions == {**sessions, "server_controls": SERVER_CONTROLS}, "method or server controls changed during arm")
    prepared = read_json(run_dir / f"{prefix}prepared_statements.json")
    verify_prepared(prepared, arm)
    plans = read_jsonl(run_dir / f"{prefix}plan_assertions.jsonl")
    require(len(plans) == 15 and {(row["method"], row["filter_threshold"]) for row in plans} ==
            {(m, t) for m in METHODS for t in FILTERS}, "plan matrix incomplete")
    lookup = {}
    for plan in plans:
        method, threshold = plan["method"], plan["filter_threshold"]
        plan_id = hashlib.sha256(f"m2-plan-v1|100000|{method}|{threshold}|{warmup_query}".encode()).hexdigest()[:20]
        raw_path = f"plans/{prefix}{plan_id}.json"
        expected = {"build_number": build, "arm": arm, "plan_id": plan_id, "raw_plan_path": raw_path,
                    "query_id": warmup_query, "scale_rows": 100000, "backend_pid": pids[method],
                    "observed_session_settings": settings[method],
                    "plan_capture": "EXPLAIN ANALYZE EXECUTE of the workload prepared generic statement"}
        require(all(plan.get(name) == value for name, value in expected.items()), "plan provenance differs")
        audited = plan["prepared_statement"]
        require(audited.get("statement") == search_sql(method, threshold, 10).replace("%s", "$1") and
                audited.get("parameter_types") == "{vector}" and audited.get("generic_plans_before_explain") == 1 and
                audited.get("generic_plans_after_explain") == 2 and audited.get("custom_plans_before_explain") == 0 and
                audited.get("custom_plans_after_explain") == 0, "plan audit not first two generic statement uses")
        matched = [statement for statement in prepared[method] if statement["name"] == audited["name"]]
        require(len(matched) == 1 and matched[0]["statement"] == audited["statement"], "audited prepared statement replaced")
        raw = read_json(run_dir / raw_path)
        recomputed = verify_plan_document(method=method, threshold=threshold, document=raw,
                                          observed_settings=settings[method], fetched_result_count=plan["fetched_result_count"])
        require(recomputed["passed"] and all(plan.get(name) == value for name, value in recomputed.items()), "raw plan validation differs")
        require(plan["actual_rows"] == len(plan["fetched_result_ids"]) == plan["fetched_result_count"], "plan result count differs")
        lookup[(method, threshold)] = plan
    return sessions, lookup


def verify_source_commit(manifest: dict, config: dict) -> dict:
    git = manifest["git_at_start"]
    require(git.get("dirty") is False and git.get("status_porcelain") == [], "campaign did not start from clean Git")
    commit = git.get("commit", "")
    require(bool(re.fullmatch("[0-9a-f]{40}", commit)), "missing full source commit")

    def blob(name: str) -> bytes:
        return subprocess.run(["git", "show", f"{commit}:{name}"], cwd=ROOT,
                              capture_output=True, check=True).stdout

    source_protocol = json.loads(blob(config["source_protocol"]))
    require(manifest.get("source_protocol") == source_protocol, "embedded source protocol differs from commit")
    require(json.loads(blob(PROTOCOL_PATH.relative_to(ROOT).as_posix())) == config,
            "experiment configuration differs from recorded source commit")
    names = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", "experiments", "sql", "config", "tests",
         "requirements-milestone2.txt", "data/sift1m/source_manifest.json"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    ).stdout.splitlines()
    expected = {name: hashlib.sha256(blob(name)).hexdigest() for name in names}
    require(manifest.get("source_file_sha256") == expected, "tracked experiment source hash inventory differs from commit")
    return source_protocol


def verify_run(run_dir: Path, *, dataset_path: Path | None = None) -> dict[str, Any]:
    """Verify a finalized run without connecting to PostgreSQL or writing files."""
    run_dir = Path(run_dir).resolve()
    hashes_before = verify_manifest(run_dir)
    marker_digest = sha256_file(run_dir / "COMPLETE.json")
    manifest_digest = sha256_file(run_dir / "checksums.sha256")
    required = {
        "config.json", "manifest.json", "dataset_manifest.json", "scale_manifest.json", "queries.json",
        "schedule.json", "environment.json", "power_before.json", "power_after.json", "executions.jsonl",
        "preparation.jsonl", "journal_manifest.json", "validation_report.json", "run.log",
        "concurrency_checks.json",
    }
    for build in (1, 2):
        required.update(f"b{build}_{suffix}" for suffix in (
            "identity.json", "database_evidence.json", "source_vector_samples.json", "ground_truth.jsonl",
            "ground_truth_reexecution.json", "ground_truth_validation.json", "phase_metrics.json"))
        for arm in ("A", "B"):
            required.update(f"b{build}_{arm}_{suffix}" for suffix in (
                "identity_before.json", "identity_after.json", "cache_reset.json", "method_sessions.json", "method_sessions_after.json",
                "prepared_statements.json", "plan_assertions.jsonl", "resource_snapshots.json"))
    require(required <= hashes_before.keys(), f"missing required payloads: {sorted(required - hashes_before.keys())}")
    config = read_json(run_dir / "config.json")
    require(sha256_json(config) == sha256_json(load_protocol()), "configuration differs from frozen preparation policy")
    digest = sha256_json(config)
    require(run_dir.name.endswith(f"_{digest[:12]}"), "run ID does not include config digest")
    manifest, complete = read_json(run_dir / "manifest.json"), read_json(run_dir / "COMPLETE.json")
    for document in (manifest, complete):
        require(document.get("run_id") == run_dir.name and document.get("config_sha256") == digest
                and document.get("research_conclusion_authorized") is False, "run scope or identity differs")
    require(complete.get("valid") is True and complete.get("measured_executions") == 60000 and
            complete.get("preparation_executions") == 7200, "completion counts or validity differ")
    source_protocol = verify_source_commit(manifest, config)
    source = source_protocol["dataset"]
    dataset = read_json(run_dir / "dataset_manifest.json")
    dataset_path = Path(dataset_path) if dataset_path is not None else Path(dataset["path"])
    observed = validate_hdf5(dataset_path, expected_sha256=source["expected_sha256"])
    require(observed["byte_size"] == source["expected_bytes"], "source dataset size differs")
    for name in ("sha256", "byte_size", "groups", "attributes", "zero_based_sentinel",
                 "values_normalized", "base_ids_zero_based", "validation_passed"):
        require(dataset.get(name) == observed[name], f"source dataset {name} differs")
    require(dataset.get("source_manifest_identity_validation") ==
            validate_source_manifest_identity(dataset["canonical_source"], source), "source manifest validation differs")
    environment = read_json(run_dir / "environment.json")
    versions = environment["database_versions"]
    require(versions.get("postgresql_version") == "17.11" and versions.get("postgresql_version_num") == "170011"
            and versions.get("pgvector_version") == "0.8.6", "incorrect database versions")
    require(environment.get("server_controls") == SERVER_CONTROLS, "server controls differ")
    for stage in ("before", "after"):
        require(read_json(run_dir / f"power_{stage}.json").get("ac_power_detected") is True, "AC power gate failed")

    assignment = source_protocol["scale_assignment"]
    order = deterministic_id_order(assignment["base_count"], "sift-base-v1|")
    order_digest = hashlib.sha256(order.astype("<i4").tobytes()).hexdigest()
    require(order_digest == assignment["expected_ordered_ids_sha256"], "global source scale ordering differs")
    selected = build_scale_manifest(order, 100000, FILTERS)
    scale = read_json(run_dir / "scale_manifest.json")
    for name, value in selected.items():
        if not isinstance(value, np.ndarray):
            require(scale.get(name) == value, f"scale {name} differs")
    require(scale["global_order"].get("ordered_ids_sha256") == order_digest and
            scale["global_order"].get("cache_sha256") == assignment["expected_cache_sha256"], "scale cache identity differs")
    scale_sha = sha256_json({name: value for name, value in scale.items() if name != "scale_manifest_sha256"})
    require(scale.get("scale_manifest_sha256") == scale_sha, "scale manifest digest differs")
    query_manifest = read_json(run_dir / "queries.json")
    expected_queries = select_query_ids()
    require(all(query_manifest.get(name) == value for name, value in expected_queries.items()), "query selection differs")
    measured, warmup = expected_queries["measured_query_ids"], expected_queries["warmup_query_ids"]
    queries = load_query_vectors(dataset_path, measured + warmup)
    require(query_manifest.get("vector_sha256") == {
        str(query): hashlib.sha256(np.asarray(vector, dtype="<f4").tobytes()).hexdigest()
        for query, vector in queries.items()}, "query-vector hashes differ")
    schedule = read_json(run_dir / "schedule.json")
    require(schedule == build_schedule(config, measured), "stored schedule differs from frozen reconstruction")
    vectors = load_scale_vectors(dataset_path, selected["selected_base_ids"])
    positions = {int(identifier): n for n, identifier in enumerate(selected["selected_base_ids"])}
    buckets = {int(identifier): int(bucket) for identifier, bucket in
               zip(selected["selected_base_ids"], selected["filter_buckets"], strict=True)}
    source_digest = source_stream_checksum(selected["selected_base_ids"], vectors, selected["filter_buckets"])
    truths, identities, session_by_arm, plan_by_arm = {}, {}, {}, {}
    for build in (1, 2):
        identities[build] = read_json(run_dir / f"b{build}_identity.json")
        validate_identity(identities[build])
        database = read_json(run_dir / f"b{build}_database_evidence.json")
        verify_database(database, selected, source_digest)
        sample_positions = np.linspace(0, 99999, 100, dtype=int)
        require(read_json(run_dir / f"b{build}_source_vector_samples.json") == {
            "sample_count": 100, "ids": sorted(int(selected["selected_base_ids"][p]) for p in sample_positions),
            "float32_exact_equality": True, "normalization_applied": False}, "source sample evidence differs")
        phases = read_json(run_dir / f"b{build}_phase_metrics.json")
        for name in ("copy_exact_ns", "copy_hnsw_from_exact_ns", "exact_index_ns", "hnsw_build_ns",
                     "vacuum_analyze_checkpoint_ns", "ground_truth_generation_ns",
                     "ground_truth_determinism_reexecution_ns", "independent_ground_truth_validation_ns"):
            require(type(phases.get(name)) is int and phases[name] > 0, f"invalid phase duration: {name}")
        require(phases.get("hnsw_build_settings") == {"maintenance_work_mem": "1GB", "max_parallel_maintenance_workers": "0"},
                "HNSW build resource controls differ")
        truths[build] = verify_truth(
            read_jsonl(run_dir / f"b{build}_ground_truth.jsonl"), run_id=run_dir.name,
            dataset_sha=source["expected_sha256"], scale_sha=scale_sha, selected=selected,
            query_ids=measured, vectors=vectors, queries=queries,
            reexecution=read_json(run_dir / f"b{build}_ground_truth_reexecution.json"),
            independent=read_json(run_dir / f"b{build}_ground_truth_validation.json"),
        )
        for arm in ("A", "B"):
            sessions, plans = verify_arm(run_dir, build, arm, identities[build], warmup[0])
            session_by_arm[(build, arm)], plan_by_arm[(build, arm)] = sessions, plans
            for (method, threshold), plan in plans.items():
                audit_row = {"result_ids": plan["fetched_result_ids"], "distances": plan["fetched_result_distances"],
                             "filter_threshold": threshold, "method": method}
                count = len(audit_row["result_ids"])
                audit_row.update(returned_count=count, returned_k=count == 10, shortfall=10 - count,
                                 ids_unique=True, scale_valid=True, filter_valid=True, distance_order_valid=True,
                                 canonical_recall_at_10=None, tie_aware_recall_at_10=None, ground_truth_record_sha256=None)
                validate_results(audit_row, buckets, None)
                require(method != "exact" or count == 10, "exact audit incomplete")
                verify_distances(audit_row, vectors, positions, queries[warmup[0]])
    for field in ("system_identifier", "database", "server_version_num", "postmaster_started_at"):
        require(identities[1][field] == identities[2][field], "cluster/postmaster changed across builds")
    first, second = validate_identity(identities[1]), validate_identity(identities[2])
    require(all(first[name][field] != second[name][field] for name in RELATIONS for field in ("oid", "filenode")),
            "physical relations reused across graph builds")
    require(truths[1] == truths[2], "ground truth differs across identical physical scales")
    require(len(list((run_dir / "plans").glob("*.json"))) == 60, "wrong raw plan file count")

    executions, preparation = read_jsonl(run_dir / "executions.jsonl"), read_jsonl(run_dir / "preparation.jsonl")
    require(len(executions) == 60000 and len(preparation) == 7200, "incorrect observation counts")
    verify_schedule_rows(executions, preparation, schedule, measured, warmup)
    journal = read_json(run_dir / "journal_manifest.json")
    require(journal.get("hard_kill_loss_bound") == "active pass" and
            journal.get("caught_interruption_completed_rows_preserved") is True and
            journal.get("query_timer_excludes_checkpoint_writes") is True, "journal durability claims differ")
    verify_chunks(run_dir, journal, executions, preparation)
    chronological = sorted(executions + preparation, key=lambda row: row["sequence_index"])
    previous_end = 0
    for row in chronological:
        build, arm, method, threshold, query = (row[name] for name in
                                                ("build_number", "arm", "method", "filter_threshold", "query_id"))
        sessions = session_by_arm[(build, arm)]
        plan = plan_by_arm[(build, arm)][(method, threshold)]
        verify_row_provenance(row, run_dir.name, digest, sessions["backend_pids"][method], plan["plan_id"])
        require(row["start_monotonic_ns"] >= previous_end, "overlapping or backwards query clock")
        previous_end = row["start_monotonic_ns"] + row["duration_ns"]
        truth = None if row["phase"] == "disjoint_warmup" else truths[build][(query, threshold)]
        validate_results(row, buckets, truth)
        require(method != "exact" or row["returned_k"], "exact warm-up incomplete")
        verify_distances(row, vectors, positions, queries[query])
    for build in (1, 2):
        for arm in ("A", "B"):
            snapshots = read_json(run_dir / f"b{build}_{arm}_resource_snapshots.json")
            chunks = [chunk for chunk in journal["chunks"] if chunk["file"].startswith(f"chunk_b{build}_{arm}_")]
            require(len(snapshots) == len(chunks) == (90 if arm == "A" else 105), "resource snapshot coverage differs")
            for snapshot, chunk in zip(snapshots, chunks, strict=True):
                last_row = chronological[chunk["last_sequence_index"] - 1]
                require(snapshot.get("after_sequence_index") == last_row["sequence_index"] and
                        all(snapshot.get(name) == last_row[name] for name in ("block_index", "phase", "repetition")),
                        "resource snapshot sequence differs")
    concurrency = read_json(run_dir / "concurrency_checks.json")
    require(concurrency.get("advisory_lock_key") == 73120412026 and concurrency.get("lock_held_until_campaign_end") is True,
            "campaign isolation lock evidence differs")
    checks = concurrency.get("checks", [])
    expected_checks = [("campaign_start", [])]
    for build in schedule["builds"]:
        number = build["build_number"]
        expected_checks.append((f"b{number}_load", []))
        for arm in build["arms"]:
            expected_checks.extend(((f"b{number}_{arm}_reset", []),
                                    (f"b{number}_{arm}_end", sorted(session_by_arm[(number, arm)]["backend_pids"].values()))))
    require(len(checks) == len(expected_checks), "client-boundary checks incomplete")
    for check, (phase, allowed) in zip(checks, expected_checks, strict=True):
        require(check.get("phase") == phase and check.get("allowed_method_pids") == allowed,
                "client-boundary check identity differs")
        clients = check.get("other_clients", [])
        require(sorted(row["pid"] for row in clients) == allowed, "unexpected or missing clients at measured boundary")
    validation = read_json(run_dir / "validation_report.json")
    expected_validation = {"passed": True, "run_id": run_dir.name, "measured_executions": 60000,
                           "preparation_executions": 7200, "plan_audits": 60, "independent_ground_truth_checks": 40,
                           "ground_truth_records": 2000, "source_unchanged": True,
                           "independent_offline_verification_required_before_interpretation": True}
    require(all(validation.get(name) == value for name, value in expected_validation.items()), "producer validation record differs")
    require(verify_manifest(run_dir) == hashes_before and sha256_file(run_dir / "COMPLETE.json") == marker_digest
            and sha256_file(run_dir / "checksums.sha256") == manifest_digest, "evidence changed during offline verification")
    require(sha256_file(dataset_path) == source["expected_sha256"], "source dataset changed during verification")
    return {"passed": True, "run_id": run_dir.name, "source_commit": manifest["git_at_start"]["commit"],
            "config_sha256": digest, "measured_executions": len(executions), "preparation_executions": len(preparation),
            "ground_truth_records": 2000, "fresh_numpy_checks": 40, "plan_audits": 60,
            "physical_graph_builds": 2, "paired_arms_per_graph": 2, "complete_payload_files": len(hashes_before),
            "input_checksums_unchanged": True, "source_distances_checked": 67260,
            "independence_scope": "Independent recall, grids, provenance and artifact checks; shared source selection, plan and NumPy helpers.",
            "latency_stability_asserted": False, "cache_cause_identified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--dataset", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(verify_run(arguments.run_dir, dataset_path=arguments.dataset), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
