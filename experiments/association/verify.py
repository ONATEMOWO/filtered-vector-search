"""Read-only, fail-closed verification of one metadata-association stage.

Metadata ranks and source-neighbor results are independently reconstructed here.
Checksum coverage, result arithmetic, source selection, plan assertions, and the
sampled NumPy truth checks reuse explicitly identified audited helpers. This is
not a wholly independent implementation of every producer operation.
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
from experiments.milestone2.dataset import (
    build_scale_manifest, deterministic_id_order, load_query_vectors,
    load_scale_vectors, select_query_ids, validate_hdf5,
    validate_source_manifest_identity,
)
from experiments.milestone2.ground_truth import (
    ground_truth_index, select_validation_keys, validate_ground_truth_numpy,
)
from experiments.preparation.protocol import SERVER_CONTROLS, SESSION_CONTROLS
from experiments.preparation.verify import (
    read_json, read_jsonl, require, validate_results, verify_chunks,
    verify_distances, verify_manifest,
)
from .protocol import FILTERS, METHODS, MODES, ROOT, STAGES, schedule, validate_config


def independent_buckets(base_ids: np.ndarray, vectors: np.ndarray, anchor: np.ndarray) -> dict[str, np.ndarray]:
    """Rank (squared float64 L2 to train[0], base ID) in each consecutive 100 rows."""
    identifiers = np.asarray(base_ids)
    values = np.asarray(vectors, dtype=np.float64)
    origin = np.asarray(anchor, dtype=np.float64)
    require(identifiers.ndim == 1 and len(identifiers) > 0 and len(identifiers) % 100 == 0,
            "metadata requires nonempty complete blocks of 100")
    require(np.issubdtype(identifiers.dtype, np.integer) and np.all(identifiers >= 0),
            "metadata source IDs must be nonnegative integers")
    require(values.shape == (len(identifiers), 128) and origin.shape == (128,),
            "metadata vector/anchor dimensions differ")
    require(len(set(map(int, identifiers))) == len(identifiers) and np.isfinite(values).all()
            and np.isfinite(origin).all(), "invalid metadata source IDs or vectors")
    distances = np.sum((values - origin) ** 2, axis=1, dtype=np.float64)
    require(np.isfinite(distances).all(), "metadata squared distances overflowed")
    radial = np.empty(len(identifiers), dtype=np.int16)
    for start in range(0, len(identifiers), 100):
        # Python tuple sorting is independent of the producer's NumPy sorting.
        positions = sorted(range(start, start + 100), key=lambda i: (float(distances[i]), int(identifiers[i])))
        for rank, position in enumerate(positions):
            radial[position] = rank
    return {"legacy": (np.arange(len(identifiers)) % 100).astype(np.int16), "radial": radial}


def validate_identity(identity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from .database import RELATIONS
    expected = dict(RELATIONS)
    rows = identity.get("relations", [])
    found = {row.get("relation"): row for row in rows}
    require(len(rows) == len(expected) and {name: row.get("kind") for name, row in found.items()} == expected,
            "physical relation matrix differs")
    for field in ("oid", "filenode"):
        values = [row.get(field) for row in rows]
        require(all(type(value) is int and value > 0 for value in values) and len(set(values)) == len(rows),
                f"invalid physical {field}")
    require(identity.get("schema") == "association" and identity.get("server_version_num") == "170011" and bool(identity.get("system_identifier"))
            and bool(identity.get("database")) and bool(identity.get("postmaster_started_at")),
            "missing or wrong cluster/version identity")
    return found


def verify_prepared(prepared: dict, mode: str) -> None:
    from .database import search_sql
    require(mode in MODES and set(prepared) == set(METHODS), "prepared mode/method matrix differs")
    for method in METHODS:
        rows = prepared[method]
        expected = {search_sql(method, mode, threshold).replace("%s", "$1") for threshold in FILTERS}
        require(len(rows) == 5 and {row["statement"] for row in rows} == expected,
                "prepared SQL matrix differs")
        require(len({row["name"] for row in rows}) == 5, "duplicate prepared names")
        for row in rows:
            require(row.get("parameter_types") == "{vector}" and row.get("generic_plans") == 1022
                    and type(row.get("generic_plans")) is int and row.get("custom_plans") == 0
                    and type(row.get("custom_plans")) is int, "prepared execution counts or parameter types differ")


def verify_schedule_rows(executions: list, preparation: list, frozen: dict, config: dict,
                         measured_ids: list[int], warmup_ids: list[int]) -> None:
    expected = []
    require(frozen["modes"] == (list(MODES) if config["build_number"] == 1 else list(reversed(MODES))),
            "incorrect metadata mode order")
    for mode in frozen["modes"]:
        for block in frozen["blocks"]:
            common = (config["scale_rows"], config["build_number"], mode,
                      block["block_index"], block["method"], block["filter_threshold"])
            expected.extend((*common, "disjoint_warmup", 0, query) for query in warmup_ids)
            require(len(block["query_order_by_repetition"]) == 5, "incomplete repetition schedule")
            for repetition, order in enumerate(block["query_order_by_repetition"], 1):
                require(sorted(order) == sorted(measured_ids), "invalid measured query permutation")
                expected.extend((*common, "measured", repetition, query) for query in order)
    for rows, phase in ((executions, "measured"), (preparation, "disjoint_warmup")):
        require(all(row.get("phase") == phase for row in rows), "observation in wrong phase file")
        require(all(type(row.get("sequence_index")) is int for row in rows), "invalid sequence index")
        require([row["sequence_index"] for row in rows] == sorted(row["sequence_index"] for row in rows),
                "consolidation is not chronological")
    rows = sorted(executions + preparation, key=lambda row: row["sequence_index"])
    require([row["sequence_index"] for row in rows] == list(range(1, len(expected) + 1)),
            "missing or duplicated chronological execution")
    fields = ("scale_rows", "build_number", "metadata_mode", "block_index", "method",
              "filter_threshold", "phase", "repetition", "query_id")
    require([tuple(row.get(name) for name in fields) for row in rows] == expected,
            "execution order differs from frozen schedule")


def verify_row_provenance(row: dict, run_id: str, digest: str, config: dict, pid: int, plan_id: str) -> None:
    from .database import search_sql
    statement = search_sql(row["method"], row["metadata_mode"], row["filter_threshold"])
    expected = {"schema_version": 1, "run_id": run_id, "config_sha256": digest, "scale_rows": config["scale_rows"],
                "build_number": config["build_number"], "k": 10, "prepared": True,
                "backend_pid": pid, "plan_audit_id": plan_id,
                "sql_sha256": hashlib.sha256(statement.encode()).hexdigest()}
    require(statement.count("%s") == 1 and all(row.get(k) == v for k, v in expected.items()),
            "row SQL or provenance differs")
    require(row.get("prepared") is True and all(type(row.get(name)) is int for name in
            ("schema_version", "scale_rows", "build_number", "k", "backend_pid")), "row provenance has incorrect value types")
    require(row.get("error_type") is None and row.get("error_message") is None and row.get("timeout") is False,
            "failed execution in completed run")
    require(type(row.get("duration_ns")) is int and row["duration_ns"] > 0 and
            type(row.get("start_monotonic_ns")) is int and row["start_monotonic_ns"] > 0,
            "invalid execution timing")


def verify_source_commit(manifest: dict, config: dict) -> dict:
    git = manifest["git_at_start"]
    require(git.get("dirty") is False and git.get("status_porcelain") == [], "stage did not start from clean Git")
    commit = git.get("commit", "")
    require(bool(re.fullmatch("[0-9a-f]{40}", commit)), "missing full source commit")
    require(manifest.get("expected_source_commit") == commit, "source commit differs from frozen campaign commit")

    def blob(name: str) -> bytes:
        return subprocess.run(["git", "show", f"{commit}:{name}"], cwd=ROOT,
                              capture_output=True, check=True).stdout

    source_protocol = json.loads(blob(config["source_protocol"]))
    require(manifest.get("source_protocol") == source_protocol, "embedded source protocol differs from commit")
    require(json.loads(blob("config/metadata-association-v1.json")) ==
            {k: v for k, v in config.items() if k not in ("scale_rows", "build_number")},
            "stage configuration differs from recorded source profile")
    names = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", "experiments", "sql", "config", "tests",
         "requirements-milestone2.txt", "data/sift1m/source_manifest.json"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    ).stdout.splitlines()
    expected = {name: hashlib.sha256(blob(name)).hexdigest() for name in names}
    require(manifest.get("source_file_sha256") == expected, "tracked experiment source inventory differs from commit")
    # Interpretation imports plan, metric, source-selection and metadata helpers.
    # Their current code must match too; checking only this module is insufficient.
    require({"experiments/association/protocol.py", "experiments/association/verify.py"} <= expected.keys(),
            "recorded commit lacks association verification source")
    for name, checksum in expected.items():
        require((ROOT / name).is_file() and sha256_file(ROOT / name) == checksum,
                f"verification source differs from recorded campaign source: {name}")
    return source_protocol


def verify_database(database: dict, scale_rows: int, source_digest: str, identity: dict) -> None:
    from .database import RELATIONS, MODE_COLUMNS
    expected = {
        "scale_rows": scale_rows, "exact_count": scale_rows, "hnsw_count": scale_rows,
        "unequal_row_count": 0, "dimensions": {"minimum": 128, "maximum": 128},
        "nonfinite_vector_counts": {"exact": 0, "hnsw": 0},
        "rank_contract": {"distinct_ranks": scale_rows, "minimum": 0, "maximum": scale_rows - 1,
                          "legacy_bucket_mismatches": 0},
        "source_vector_stream_sha256": source_digest, "exact_vector_stream_sha256": source_digest,
        "hnsw_vector_stream_sha256": source_digest, "all_source_rows_and_both_metadata_equal": True,
        "identity": identity,
        "filter_counts": {mode: {str(t): {"exact": scale_rows * t // 100, "hnsw": scale_rows * t // 100,
                                          "expected": scale_rows * t // 100} for t in FILTERS} for mode in MODES},
    }
    require(all(database.get(name) == value for name, value in expected.items()),
            "physical data/source/filter evidence differs")
    indexes = database["indexes"]
    require(len(indexes) == 5 and {r["index"] for r in indexes} == {n for n, k in RELATIONS.items() if k == "i"}
            and all(r["schema"] == "association" for r in indexes), "database index matrix differs")
    for column in MODE_COLUMNS.values():
        matching = [r for r in indexes if r["index"] == f"sift_exact_{column}_idx"]
        require(len(matching) == 1 and matching[0]["table"] == "sift_exact"
                and f"USING btree ({column})" in matching[0]["definition"], "exact metadata index differs")
    graph = next(r for r in indexes if r["index"] == "sift_hnsw_embedding_idx")
    require(graph["table"] == "sift_hnsw" and all(s in graph["definition"] for s in
            ("USING hnsw (embedding vector_l2_ops)", "m='16'", "ef_construction='64'")), "HNSW graph differs")
    require(not any(r["table"] == "sift_exact" and "(embedding" in r["definition"] for r in indexes),
            "exact table has a vector index")
    stats = database["statistics"]
    require(len(stats) == 4 and {(r["table"], r["column"]) for r in stats} ==
            {(t, c) for t in ("sift_exact", "sift_hnsw") for c in MODE_COLUMNS.values()}
            and all(r["null_fraction"] == 0 and r["distinct"] == 100 for r in stats),
            "metadata planner statistics differ")
    sizes = database["relation_sizes"]
    require(len(sizes) == 7 and {r["relation"]: r["kind"] for r in sizes} == RELATIONS and
            all(type(r["relation_bytes"]) is int and r["relation_bytes"] > 0 and
                type(r["total_bytes"]) is int and r["total_bytes"] >= r["relation_bytes"] for r in sizes),
            "physical relation sizes differ")


def verify_truth(records: list, *, mode: str, metadata_sha: str, config: dict, run_id: str,
                 dataset_sha: str, base_ids: np.ndarray, buckets: np.ndarray, vectors: np.ndarray,
                 queries: dict, measured_ids: list, reexecution: dict, independent: dict) -> dict:
    from .database import ground_truth_sql
    truth = ground_truth_index(records)
    require(set(truth) == {(q, t) for q in measured_ids for t in FILTERS}, "incomplete ground-truth grid")
    bucket_map = dict(zip(map(int, base_ids), map(int, buckets), strict=True))
    positions = {int(identifier): position for position, identifier in enumerate(base_ids)}
    for (query, threshold), record in truth.items():
        identifiers, distances = record["all_with_ties_ids"], record["all_with_ties_distances"]
        require(len(identifiers) == len(distances) >= 10 and len(set(identifiers)) == len(identifiers),
                "invalid truth result lengths or duplicate IDs")
        require(all(type(i) is int and i in bucket_map and bucket_map[i] < threshold for i in identifiers),
                "truth result outside metadata filter")
        require(all(type(d) in (int, float) and math.isfinite(d) and d >= 0 for d in distances),
                "invalid truth distances")
        require(list(zip(distances, identifiers)) == sorted(zip(distances, identifiers)),
                "truth ordering differs from distance/ID canonical order")
        boundary = distances[9]
        closer = [i for i, d in zip(identifiers, distances) if d < boundary]
        tied = [i for i, d in zip(identifiers, distances) if d == boundary]
        expected = {
            "schema_version": 1, "run_id": run_id, "dataset_sha256": dataset_sha,
            "scale_manifest_sha256": metadata_sha, "metadata_sha256": metadata_sha, "metadata_mode": mode,
            "scale_rows": config["scale_rows"], "filter_threshold": threshold,
            "qualifying_count": config["scale_rows"] * threshold // 100, "query_id": query, "k": 10,
            "generation_method": "PostgreSQL exact filtered L2 search on association.sift_exact with no vector index",
            "generation_sql": ground_truth_sql(mode, threshold), "canonical_ids": identifiers[:10],
            "canonical_distances": distances[:10], "boundary_distance": boundary,
            "strictly_closer_ids": closer, "boundary_tie_ids": tied,
        }
        require(max(distances) == boundary and len(closer) < 10 <= len(closer) + len(tied)
                and all(record.get(name) == value for name, value in expected.items()),
                "ground-truth mode/provenance/boundary partition differs")
        verify_distances({"result_ids": identifiers, "distances": distances}, vectors, positions, queries[query])
    require(reexecution.get("passed") is True and reexecution.get("metadata_mode") == mode
            and reexecution.get("reexecuted_records") == 1000
            and reexecution.get("record_checksums_identical_in_order") is True
            and type(reexecution.get("duration_ns")) is int and reexecution["duration_ns"] > 0,
            "ground-truth reexecution evidence incomplete")
    recalculated = validate_ground_truth_numpy(
        records=truth, validation_keys=select_validation_keys(measured_ids, FILTERS, 20),
        base_ids=base_ids, vectors=vectors, buckets=buckets, query_vectors=queries, k=10,
    )
    require(independent == recalculated, "fresh sampled NumPy truth verification differs")
    return truth


def verify_mode(run_dir: Path, mode: str, config: dict, identity: dict, warmup_query: int) -> tuple[dict, dict]:
    from .database import search_sql, verify_plan_document
    before = read_json(run_dir / f"{mode}_identity_before.json")
    after = read_json(run_dir / f"{mode}_identity_after.json")
    validate_identity(before)
    validate_identity(after)
    require(identity == before == after, "physical graph/cluster/postmaster changed between metadata modes")
    reset = read_json(run_dir / f"{mode}_cache_reset.json")
    require(reset.get("operating_system_cache_flushed") is False and reset.get("postmaster_restarted") is False,
            "cache reset falsely claims restart or OS-cache flush")
    require(reset.get("method") == "pg_buffercache_evict over a materialized buffer-id snapshot after CHECKPOINT"
            and reset.get("after", {}).get("buffers_used") == 0, "shared-buffer eviction did not succeed")
    sessions = read_json(run_dir / f"{mode}_method_sessions.json")
    pids, settings = sessions["backend_pids"], sessions["settings"]
    require(set(pids) == set(settings) == set(METHODS) and len(set(pids.values())) == 3 and
            all(type(pid) is int and pid > 0 for pid in pids.values()), "invalid persistent method sessions")
    for method, observed in settings.items():
        expected = {**SESSION_CONTROLS, "work_mem": "4MB" if method == "exact" else "64MB",
                    "jit": "off", "plan_cache_mode": "force_generic_plan", "statement_timeout": "2min"}
        require(all(observed.get(name) == value for name, value in expected.items()), "session controls differ")
    require(read_json(run_dir / f"{mode}_method_sessions_after.json") == {**sessions, "server_controls": SERVER_CONTROLS},
            "session/server controls changed during mode")
    prepared = read_json(run_dir / f"{mode}_prepared_statements.json")
    verify_prepared(prepared, mode)
    plans = read_jsonl(run_dir / f"{mode}_plan_assertions.jsonl")
    require(len(plans) == 15 and {(r["method"], r["filter_threshold"]) for r in plans} ==
            {(m, t) for m in METHODS for t in FILTERS}, "plan matrix incomplete")
    lookup = {}
    for plan in plans:
        method, threshold = plan["method"], plan["filter_threshold"]
        plan_id = hashlib.sha256(f"association-plan-v1|{config['scale_rows']}|{method}|{mode}|{threshold}|{warmup_query}".encode()).hexdigest()[:20]
        raw_path = f"plans/{mode}_{plan_id}.json"
        expected = {"build_number": config["build_number"], "metadata_mode": mode,
                    "scale_rows": config["scale_rows"], "plan_id": plan_id, "raw_plan_path": raw_path,
                    "query_id": warmup_query, "backend_pid": pids[method],
                    "observed_session_settings": settings[method],
                    "expected_index": None if method == "exact" else "sift_hnsw_embedding_idx",
                    "plan_capture": "EXPLAIN ANALYZE VERBOSE EXECUTE of the workload prepared generic statement"}
        require(all(plan.get(k) == v for k, v in expected.items()), "plan provenance differs")
        audited = plan["prepared_statement"]
        require(audited.get("statement") == search_sql(method, mode, threshold).replace("%s", "$1")
                and audited.get("parameter_types") == "{vector}"
                and audited.get("generic_plans_before_explain") == 1 and audited.get("generic_plans_after_explain") == 2
                and audited.get("custom_plans_before_explain") == 0 and audited.get("custom_plans_after_explain") == 0,
                "plan audit is not first two uses of one generic vector statement")
        matched = [r for r in prepared[method] if r["name"] == audited["name"]]
        require(len(matched) == 1 and matched[0]["statement"] == audited["statement"], "audited prepared statement replaced")
        recomputed = verify_plan_document(method=method, mode=mode, threshold=threshold,
                                          document=read_json(run_dir / raw_path), observed_settings=settings[method],
                                          fetched_result_count=plan["fetched_result_count"])
        require(recomputed["passed"] and all(plan.get(k) == v for k, v in recomputed.items()), "raw plan validation differs")
        require(plan["actual_rows"] == len(plan["fetched_result_ids"]) == len(plan["fetched_result_distances"])
                == plan["fetched_result_count"], "plan result count differs")
        lookup[(method, threshold)] = plan
    return sessions, lookup


def verify_prefix_hashes(manifest: dict, base_ids: np.ndarray, radial: np.ndarray) -> None:
    """Authenticate prefix invariance without trusting the producer's assertion."""
    fields = ("prefix_100k_ordered_base_ids_int64_le_sha256", "prefix_100k_radial_labels_int16_le_sha256")
    if len(base_ids) >= 100000:
        for name, values, dtype in zip(fields, (base_ids, radial), ("<i8", "<i2"), strict=True):
            expected = hashlib.sha256(np.asarray(values[:100000], dtype=dtype).tobytes()).hexdigest()
            require(manifest.get(name) == expected, f"metadata 100k prefix differs: {name}")
    else:
        require(not any(name in manifest for name in fields), "metadata claims nonexistent 100k prefix")


def verify_metadata(manifest: dict, base_ids: np.ndarray, vectors: np.ndarray, anchor: np.ndarray) -> dict:
    """Do not call the metadata producer to establish its correctness."""
    labels = independent_buckets(base_ids, vectors, anchor)
    n = len(base_ids)
    values = np.asarray(vectors, dtype=np.float64)
    scores = np.sum((values - np.asarray(anchor, dtype=np.float64)) ** 2, axis=1, dtype=np.float64)

    def digest(values, dtype):
        return hashlib.sha256(np.asarray(values, dtype=dtype).tobytes()).hexdigest()

    sorted_scores = np.empty((n // 100, 100), dtype=np.float64)
    for start in range(0, n, 100):
        for position in range(start, start + 100):
            sorted_scores[start // 100, labels["radial"][position]] = scores[position]
    boundaries = {}
    for threshold in FILTERS:
        included, excluded = sorted_scores[:, threshold - 1], sorted_scores[:, threshold]
        boundaries[str(threshold)] = {
            "last_included_squared_distance_min": float(min(included)),
            "last_included_squared_distance_median": float(np.median(included)),
            "last_included_squared_distance_max": float(max(included)),
            "first_excluded_squared_distance_min": float(min(excluded)),
            "first_excluded_squared_distance_median": float(np.median(excluded)),
            "first_excluded_squared_distance_max": float(max(excluded)),
            "boundary_tied_block_count": int(np.count_nonzero(included == excluded)),
            "all_block_boundary_pairs_sha256": digest(np.column_stack((included, excluded)), "<f8"),
        }
    expected = {
        "schema_version": 1, "algorithm": "fixed-anchor-squared-l2-within-consecutive-100-rank-blocks-v1",
        "row_count": n, "dimension": 128, "block_size": 100, "block_count": n // 100,
        "anchor_source_base_id": 0, "anchor_vector": np.asarray(anchor, dtype=np.float64).tolist(),
        "anchor_float64_le_sha256": digest(anchor, "<f8"), "ordered_base_ids_int64_le_sha256": digest(base_ids, "<i8"),
        "radial_labels_int16_le_sha256": digest(labels["radial"], "<i2"),
        "scores_float64_le_sha256": digest(scores, "<f8"),
        "filter_counts": {str(t): n * t // 100 for t in FILTERS},
        "squared_score_min": float(min(scores)), "squared_score_max": float(max(scores)),
        "score_boundary_summary_by_filter": boundaries,
    }
    verify_prefix_hashes(manifest, base_ids, labels["radial"])
    require(all(manifest.get(name) == value for name, value in expected.items()),
            "metadata differs from independent fixed-anchor/block-rank reconstruction")
    return labels


def verify_neighbors(records: list, base_ids: np.ndarray, vectors: np.ndarray, queries: dict,
                     labels: dict, anchor: np.ndarray) -> None:
    require([r.get("query_id") for r in records] == sorted(queries), "neighborhood query grid/order differs")
    ids = np.asarray(base_ids, dtype=np.int64)
    values = np.asarray(vectors, dtype=np.float64)
    require(len(ids) >= 1000, "neighborhood source is too small")
    for record in records:
        query = np.asarray(queries[record["query_id"]], dtype=np.float64)
        # Full canonical sorting is deliberately distinct from the producer's
        # partition-plus-boundary-candidate selection.
        squared = np.empty(len(ids), dtype=np.float64)
        for start in range(0, len(ids), 8192):
            squared[start:start + 8192] = np.sum((values[start:start + 8192] - query) ** 2, axis=1)
        selected = np.lexsort((ids, squared))[:1000]
        expected_counts = {mode: {str(t): {str(size): int(np.count_nonzero(labels[mode][selected[:size]] < t))
                                          for size in (40, 100, 1000)} for t in FILTERS} for mode in MODES}
        anchor_sq = float(np.sum((query - np.asarray(anchor, dtype=np.float64)) ** 2))
        expected = {
            "neighbor_ids": ids[selected].tolist(), "squared_distances": squared[selected].tolist(),
            "distance_computation": "direct float64 squared L2; ascending distance then base_id",
            "neighborhood_sizes": [40, 100, 1000], "local_counts": expected_counts,
            "query_anchor_squared_distance": anchor_sq, "query_anchor_distance": float(np.sqrt(anchor_sq)),
        }
        require(all(record.get(name) == value for name, value in expected.items()),
                f"independent source neighborhood differs for query {record['query_id']}")


def verify_phase_metrics(phases: dict) -> None:
    expected = ("schema_and_copy_exact_ns", "copy_hnsw_from_exact_ns", "exact_index_ns",
                "hnsw_build_ns", "vacuum_analyze_checkpoint_ns", "metadata_diagnostics_ns")
    expected += tuple(f"{mode}_{suffix}_ns" for mode in MODES for suffix in
                      ("ground_truth", "truth_reexecution", "numpy_validation"))
    for name in expected:
        require(type(phases.get(name)) is int and phases[name] > 0, f"invalid phase duration: {name}")
    require(phases.get("hnsw_build_settings") == {"maintenance_work_mem": "1GB",
            "max_parallel_maintenance_workers": "0", "m": 16, "ef_construction": 64},
            "HNSW build resource controls differ")


def verify_resources(snapshots: list, chunks: list, chronological: list) -> None:
    require(len(snapshots) == len(chunks) == 180, "resource snapshot coverage differs")
    for snapshot, chunk in zip(snapshots, chunks, strict=True):
        last = chronological[chunk["last_sequence_index"] - 1]
        require(snapshot.get("after_sequence_index") == last["sequence_index"] and
                all(snapshot.get(name) == last[name] for name in
                    ("metadata_mode", "block_index", "phase", "repetition")),
                "resource snapshot sequence differs")
        require(isinstance(snapshot.get("host"), dict) and bool(snapshot["host"]), "missing host resource snapshot")


def verify_concurrency(concurrency: dict, frozen: dict, sessions: dict) -> None:
    require(concurrency.get("advisory_lock_key") == 73120412026
            and concurrency.get("lock_held_until_stage_end") is True, "stage isolation lock evidence differs")
    expected = [("stage_start", []), ("load", [])]
    for mode in frozen["modes"]:
        expected.extend(((f"{mode}_reset", []), (f"{mode}_end", sorted(sessions[mode]["backend_pids"].values()))))
    checks = concurrency.get("checks", [])
    require(len(checks) == len(expected), "client-boundary checks incomplete")
    for check, (phase, allowed) in zip(checks, expected, strict=True):
        require(check.get("phase") == phase and check.get("allowed_method_pids") == allowed,
                "client-boundary check identity differs")
        require(sorted(r["pid"] for r in check.get("other_clients", [])) == allowed,
                "unexpected or missing client at stage boundary")


def verify_predecessor(manifest: dict, config: dict, identity: dict, metadata: dict) -> None:
    position = STAGES.index((config["scale_rows"], config["build_number"]))
    predecessor = manifest.get("predecessor")
    if position == 0:
        require(predecessor is None, "first stage incorrectly has a predecessor")
        return
    require(isinstance(predecessor, dict), "stage lacks predecessor evidence")
    previous = Path(predecessor["run_directory"])
    verify_manifest(previous)
    old_config = read_json(previous / "config.json")
    validate_config(old_config)
    require((old_config["scale_rows"], old_config["build_number"]) == STAGES[position - 1],
            "predecessor is not the previous frozen stage")
    old_manifest = read_json(previous / "manifest.json")
    old_complete = read_json(previous / "COMPLETE.json")
    require(old_complete.get("valid") is True and old_complete.get("run_id") == previous.name
            and old_complete.get("config_sha256") == sha256_json(old_config)
            and old_complete.get("research_conclusion_authorized") is False,
            "predecessor completion identity differs")
    require(old_manifest["source_file_sha256"] == manifest["source_file_sha256"],
            "matched stages changed experiment implementation")
    proof = predecessor["verification"]
    require(proof.get("passed") is True and proof.get("run_id") == previous.name
            and proof.get("config_sha256") == sha256_json(old_config)
            and proof.get("source_commit") == old_manifest["git_at_start"]["commit"],
            "predecessor verification identity differs")
    old_identity = read_json(previous / "identity.json")
    old, new = validate_identity(old_identity), validate_identity(identity)
    require(all(old_identity[k] == identity[k] for k in ("system_identifier", "database", "server_version_num")),
            "stage changed PostgreSQL cluster")
    require(all(old[name][field] != new[name][field] for name in old for field in ("oid", "filenode")),
            "physical graph or table reused from previous stage")
    old_metadata = read_json(previous / "metadata_manifest.json")
    for name in ("prefix_100k_ordered_base_ids_int64_le_sha256", "prefix_100k_radial_labels_int16_le_sha256"):
        require(name in old_metadata and old_metadata[name] == metadata.get(name),
                "100k source/metadata prefix changed between stages")


def verify_run(run_dir: Path, *, dataset_path: Path | None = None) -> dict[str, Any]:
    """Verify finalized stage evidence without connecting to PostgreSQL or writing."""
    from .database import source_stream_checksum
    from .metadata import association_diagnostics

    run_dir = Path(run_dir).resolve()
    before = verify_manifest(run_dir)
    marker_sha, manifest_sha = (sha256_file(run_dir / n) for n in ("COMPLETE.json", "checksums.sha256"))
    required = {"config.json", "manifest.json", "dataset_manifest.json", "scale_manifest.json",
                "metadata_manifest.json", "queries.json", "schedule.json", "neighbors.jsonl",
                "association_diagnostics.json", "database_evidence.json", "identity.json", "phase_metrics.json",
                "environment.json", "power_before.json", "power_after.json", "executions.jsonl",
                "preparation.jsonl", "journal_manifest.json", "resource_snapshots.json", "concurrency_checks.json",
                "validation_report.json", "run.log"}
    for mode in MODES:
        required.update(f"{mode}_{suffix}" for suffix in (
            "ground_truth.jsonl", "truth_reexecution.json", "truth_validation.json", "identity_before.json",
            "identity_after.json", "cache_reset.json", "method_sessions.json", "method_sessions_after.json",
            "prepared_statements.json", "plan_assertions.jsonl"))
    require(required <= before.keys(), f"missing required payloads: {sorted(required - before.keys())}")
    config = read_json(run_dir / "config.json")
    validate_config(config)
    digest, scale_rows = sha256_json(config), config["scale_rows"]
    require(run_dir.name.endswith(f"_{digest[:12]}"), "run ID does not include configuration digest")
    manifest, complete = read_json(run_dir / "manifest.json"), read_json(run_dir / "COMPLETE.json")
    for document in (manifest, complete):
        require(document.get("run_id") == run_dir.name and document.get("config_sha256") == digest
                and document.get("research_conclusion_authorized") is False, "run scope or identity differs")
    require(complete.get("valid") is True and complete.get("measured_executions") == 30000
            and complete.get("preparation_executions") == 600, "completion counts or validity differ")
    source_protocol = verify_source_commit(manifest, config)
    source = source_protocol["dataset"]
    dataset = read_json(run_dir / "dataset_manifest.json")
    dataset_path = Path(dataset_path) if dataset_path is not None else Path(dataset["path"])
    observed = validate_hdf5(dataset_path, expected_sha256=source["expected_sha256"])
    require(observed["byte_size"] == source["expected_bytes"], "source dataset size differs")
    for name in ("sha256", "byte_size", "groups", "attributes", "zero_based_sentinel", "values_normalized",
                 "base_ids_zero_based", "validation_passed"):
        require(dataset.get(name) == observed[name], f"source dataset {name} differs")
    require(dataset.get("source_manifest_identity_validation") ==
            validate_source_manifest_identity(dataset["canonical_source"], source), "source manifest validation differs")
    environment = read_json(run_dir / "environment.json")
    versions = environment["database_versions"]
    require(versions.get("postgresql_version") == "17.11" and versions.get("postgresql_version_num") == "170011"
            and versions.get("pgvector_version") == "0.8.6", "database versions differ")
    require(environment.get("server_controls") == SERVER_CONTROLS, "server controls differ")
    powers = [read_json(run_dir / f"power_{phase}.json") for phase in ("before", "after")]
    require(all(power.get("ac_power_detected") is True for power in powers), "AC-power gate failed")
    require(isinstance(powers[0].get("energy_settings_stdout"), str) and
            powers[0]["energy_settings_stdout"] == powers[1].get("energy_settings_stdout"),
            "power settings missing or changed during stage")
    host = environment["host"]
    require(host.get("memory_available_bytes", 0) >= config["resource_min_available_bytes"] and
            host.get("disk_free_bytes", 0) >= config["resource_min_disk_bytes"], "initial host resource gates failed")
    assignment = source_protocol["scale_assignment"]
    order = deterministic_id_order(assignment["base_count"], "sift-base-v1|")
    order_sha = hashlib.sha256(order.astype("<i4").tobytes()).hexdigest()
    require(order_sha == assignment["expected_ordered_ids_sha256"], "global scale ordering differs")
    selected = build_scale_manifest(order, scale_rows, FILTERS)
    scale = read_json(run_dir / "scale_manifest.json")
    for name, value in selected.items():
        if not isinstance(value, np.ndarray):
            require(scale.get(name) == value, f"scale {name} differs")
    require(scale["global_order"].get("ordered_ids_sha256") == order_sha and
            scale["global_order"].get("cache_sha256") == assignment["expected_cache_sha256"], "scale cache identity differs")
    query_manifest = read_json(run_dir / "queries.json")
    expected_queries = select_query_ids()
    require(all(query_manifest.get(k) == v for k, v in expected_queries.items()), "query selection differs")
    measured, warmup = expected_queries["measured_query_ids"], expected_queries["warmup_query_ids"]
    queries = load_query_vectors(dataset_path, measured + warmup)
    require(query_manifest.get("vector_sha256") == {
        str(q): hashlib.sha256(np.asarray(v, dtype="<f4").tobytes()).hexdigest() for q, v in queries.items()},
        "query-vector hashes differ")
    frozen = read_json(run_dir / "schedule.json")
    require(frozen == schedule(config, measured), "schedule differs from frozen reconstruction")
    base_ids = selected["selected_base_ids"]
    vectors = load_scale_vectors(dataset_path, base_ids)
    anchor = load_scale_vectors(dataset_path, np.asarray([0], dtype=np.int32))[0]
    metadata = read_json(run_dir / "metadata_manifest.json")
    labels = verify_metadata(metadata, base_ids, vectors, anchor)
    metadata_sha = sha256_json(metadata)
    neighbors = read_jsonl(run_dir / "neighbors.jsonl")
    verify_neighbors(neighbors, base_ids, vectors, queries, labels, anchor)
    diagnostics = association_diagnostics(neighbors, base_ids, labels["radial"], measured,
                                         seed=config["association_seed"], permutations=config["association_permutations"])
    require(read_json(run_dir / "association_diagnostics.json") == diagnostics and diagnostics["gate_passed"] is True,
            "association manipulation check does not reproduce or failed")
    identity = read_json(run_dir / "identity.json")
    validate_identity(identity)
    require(identity.get("schema") == "association", "physical identity is for wrong schema")
    verify_predecessor(manifest, config, identity, metadata)
    source_sha = source_stream_checksum(base_ids, vectors, labels["legacy"], labels["radial"])
    verify_database(read_json(run_dir / "database_evidence.json"), scale_rows, source_sha, identity)
    phases = read_json(run_dir / "phase_metrics.json")
    verify_phase_metrics(phases)
    positions = {int(identifier): n for n, identifier in enumerate(base_ids)}
    buckets = {mode: dict(zip(map(int, base_ids), map(int, labels[mode]), strict=True)) for mode in MODES}
    truths, sessions, plans = {}, {}, {}
    for mode in MODES:
        reexecution = read_json(run_dir / f"{mode}_truth_reexecution.json")
        require(reexecution.get("duration_ns") == phases[f"{mode}_truth_reexecution_ns"], "truth phase duration differs")
        truths[mode] = verify_truth(
            read_jsonl(run_dir / f"{mode}_ground_truth.jsonl"), mode=mode, metadata_sha=metadata_sha,
            config=config, run_id=run_dir.name, dataset_sha=source["expected_sha256"], base_ids=base_ids,
            buckets=labels[mode], vectors=vectors, queries=queries, measured_ids=measured,
            reexecution=reexecution, independent=read_json(run_dir / f"{mode}_truth_validation.json"))
        sessions[mode], plans[mode] = verify_mode(run_dir, mode, config, identity, warmup[0])
        for (method, threshold), plan in plans[mode].items():
            row = {"result_ids": plan["fetched_result_ids"], "distances": plan["fetched_result_distances"],
                   "filter_threshold": threshold, "method": method}
            count = len(row["result_ids"])
            row.update(returned_count=count, returned_k=count == 10, shortfall=10 - count,
                       ids_unique=True, scale_valid=True, filter_valid=True, distance_order_valid=True,
                       canonical_recall_at_10=None, tie_aware_recall_at_10=None, ground_truth_record_sha256=None)
            validate_results(row, buckets[mode], None)
            require(method != "exact" or count == 10, "exact audit incomplete")
            verify_distances(row, vectors, positions, queries[warmup[0]])
    require(len(list((run_dir / "plans").glob("*.json"))) == 30, "raw plan count differs")
    executions, preparation = read_jsonl(run_dir / "executions.jsonl"), read_jsonl(run_dir / "preparation.jsonl")
    require(len(executions) == 30000 and len(preparation) == 600, "observation counts differ")
    verify_schedule_rows(executions, preparation, frozen, config, measured, warmup)
    journal = read_json(run_dir / "journal_manifest.json")
    require(journal.get("hard_kill_loss_bound") == "active pass"
            and journal.get("caught_interruption_completed_rows_preserved") is True
            and journal.get("query_timer_excludes_checkpoint_writes") is True, "journal durability claims differ")
    verify_chunks(run_dir, journal, executions, preparation)
    chronological = sorted(executions + preparation, key=lambda r: r["sequence_index"])
    previous_end = 0
    for row in chronological:
        mode, method, threshold, query = (row[k] for k in ("metadata_mode", "method", "filter_threshold", "query_id"))
        verify_row_provenance(row, run_dir.name, digest, config, sessions[mode]["backend_pids"][method],
                              plans[mode][method, threshold]["plan_id"])
        require(row["start_monotonic_ns"] >= previous_end, "overlapping or backwards query clock")
        previous_end = row["start_monotonic_ns"] + row["duration_ns"]
        truth = None if row["phase"] == "disjoint_warmup" else truths[mode][query, threshold]
        validate_results(row, buckets[mode], truth)
        require(method != "exact" or row["returned_k"], "exact warmup incomplete")
        verify_distances(row, vectors, positions, queries[query])
    verify_resources(read_json(run_dir / "resource_snapshots.json"), journal["chunks"], chronological)
    verify_concurrency(read_json(run_dir / "concurrency_checks.json"), frozen, sessions)
    validation = read_json(run_dir / "validation_report.json")
    expected = {"passed": True, "run_id": run_dir.name, "measured_executions": 30000, "preparation_executions": 600,
                "plan_audits": 30, "ground_truth_records": 2000, "independent_ground_truth_checks": 40,
                "source_unchanged": True, "independent_offline_verification_required_before_interpretation": True}
    require(all(validation.get(k) == v for k, v in expected.items()) and
            type(validation.get("elapsed_ns")) is int and validation["elapsed_ns"] > 0, "producer validation report differs")
    require(verify_manifest(run_dir) == before and sha256_file(run_dir / "COMPLETE.json") == marker_sha and
            sha256_file(run_dir / "checksums.sha256") == manifest_sha, "evidence changed during verification")
    require(sha256_file(dataset_path) == source["expected_sha256"], "source dataset changed during verification")
    return {"passed": True, "run_id": run_dir.name, "source_commit": manifest["git_at_start"]["commit"],
            "config_sha256": digest, "scale_rows": scale_rows, "build_number": config["build_number"],
            "measured_executions": len(executions), "preparation_executions": len(preparation),
            "ground_truth_records": 2000, "fresh_numpy_checks": 40, "plan_audits": 30,
            "physical_graph_builds": 1, "metadata_modes_sharing_graph": 2,
            "source_neighborhoods_recomputed": len(neighbors), "association_gate_passed": True,
            "complete_payload_files": len(before), "input_checksums_unchanged": True,
            "source_distance_rows_checked": 30630, "latency_stability_asserted": False,
            "independence_scope": "Independent metadata, neighborhood source ranking, truth partition, schedule and provenance; reused checksum/recall/chunk/source/plan/statistic/NumPy helpers."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--dataset", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_run(args.run_dir, dataset_path=args.dataset), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
