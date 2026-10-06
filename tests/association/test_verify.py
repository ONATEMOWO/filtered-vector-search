"""Mutation-focused offline verification tests; no PostgreSQL or SIFT reads."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from experiments.association import database as db, metadata, verify
from experiments.association.protocol import FILTERS, METHODS, MODES, stage_config
from experiments.milestone2.config import canonical_json_bytes, sha256_json
from experiments.milestone2.ground_truth import select_validation_keys, validate_ground_truth_numpy
from experiments.preparation.protocol import SERVER_CONTROLS, SESSION_CONTROLS
from tests.association.test_database import ann_plan, exact_plan, settings


def physical_identity(offset=0):
    return {"schema": "association", "server_version_num": "170011", "database": "test",
            "system_identifier": "cluster", "postmaster_started_at": "2026-10-06T00:00:00+00:00",
            "relations": [{"relation": name, "kind": kind, "oid": offset + i, "filenode": offset + i + 10}
                          for i, (name, kind) in enumerate(db.RELATIONS.items(), 1)]}


def prepared_fixture(mode):
    return {method: [{"name": f"statement_{t}", "statement": db.search_sql(method, mode, t).replace("%s", "$1"),
                      "parameter_types": "{vector}", "generic_plans": 1022, "custom_plans": 0}
                     for t in FILTERS] for method in METHODS}


def synthetic_vectors(count=1000):
    # Small integer coordinates exactly representable by both reduction paths.
    ids = np.arange(count - 1, -1, -1, dtype=np.int32)
    vectors = np.zeros((count, 128), dtype=np.float32)
    vectors[:, 0] = np.arange(count) % 200
    vectors[:, 1] = np.arange(count) // 200
    return ids, vectors, np.zeros(128, dtype=np.float32)


def write_json(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def rehash(record):
    record["record_sha256"] = hashlib.sha256(canonical_json_bytes(
        {k: v for k, v in record.items() if k != "record_sha256"})).hexdigest()


def physical_evidence():
    n = 100000
    indexes = [{"schema": "association", "table": table, "index": f"{table}_pkey",
                "definition": f"CREATE UNIQUE INDEX {table}_pkey ON association.{table} USING btree (id)"}
               for table in ("sift_exact", "sift_hnsw")]
    indexes.extend({"schema": "association", "table": "sift_exact", "index": f"sift_exact_{column}_idx",
                    "definition": f"CREATE INDEX sift_exact_{column}_idx ON association.sift_exact USING btree ({column})"}
                   for column in db.MODE_COLUMNS.values())
    indexes.append({"schema": "association", "table": "sift_hnsw", "index": db.HNSW_INDEX,
                    "definition": "CREATE INDEX sift_hnsw_embedding_idx ON association.sift_hnsw USING hnsw (embedding vector_l2_ops) WITH (m='16', ef_construction='64')"})
    return {"scale_rows": n, "exact_count": n, "hnsw_count": n, "unequal_row_count": 0,
            "dimensions": {"minimum": 128, "maximum": 128}, "nonfinite_vector_counts": {"exact": 0, "hnsw": 0},
            "rank_contract": {"distinct_ranks": n, "minimum": 0, "maximum": n - 1, "legacy_bucket_mismatches": 0},
            "source_vector_stream_sha256": "source", "exact_vector_stream_sha256": "source", "hnsw_vector_stream_sha256": "source",
            "all_source_rows_and_both_metadata_equal": True, "identity": physical_identity(), "indexes": indexes,
            "filter_counts": {mode: {str(t): {"exact": n * t // 100, "hnsw": n * t // 100, "expected": n * t // 100}
                                     for t in FILTERS} for mode in MODES},
            "statistics": [{"table": table, "column": column, "null_fraction": 0, "distinct": 100}
                           for table in ("sift_exact", "sift_hnsw") for column in db.MODE_COLUMNS.values()],
            "relation_sizes": [{"relation": name, "kind": kind, "relation_bytes": 8192, "total_bytes": 16384}
                               for name, kind in db.RELATIONS.items()]}


class MetadataVerificationTests(unittest.TestCase):
    def test_independent_block_ranks_and_manifest_match_producer(self):
        ids, vectors, anchor = synthetic_vectors(200)
        radial, manifest = metadata.build_metadata(ids, vectors, anchor)
        found = verify.verify_metadata(manifest, ids, vectors, anchor)
        np.testing.assert_array_equal(found["radial"], radial)
        np.testing.assert_array_equal(found["legacy"], np.arange(200) % 100)
        for field, wrong in (("dimension", 127), ("row_count", 100), ("anchor_source_base_id", 1),
                             ("scores_float64_le_sha256", "wrong"), ("radial_labels_int16_le_sha256", "wrong"),
                             ("filter_counts", {"50": 50}), ("score_boundary_summary_by_filter", {})):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                verify.verify_metadata({**manifest, field: wrong}, ids, vectors, anchor)

    def test_equal_scores_are_broken_by_base_id_not_row_order(self):
        ids, vectors, anchor = synthetic_vectors(100)
        vectors[:] = 0
        result = verify.independent_buckets(ids, vectors, anchor)
        np.testing.assert_array_equal(result["radial"], np.arange(99, -1, -1))

    def test_bad_ids_dimensions_and_nonfinite_vectors_rejected(self):
        ids, vectors, anchor = synthetic_vectors(100)
        for identifiers, values, origin in ((ids.astype(float), vectors, anchor),
                                            (np.zeros(100, dtype=np.int32), vectors, anchor),
                                            (ids, vectors[:, :127], anchor[:127]),
                                            (ids, vectors + np.nan, anchor),
                                            (ids - 100, vectors, anchor)):
            with self.subTest(), self.assertRaises(AssertionError):
                verify.independent_buckets(identifiers, values, origin)

    def test_100k_prefix_hashes_required_and_independent_of_suffix(self):
        ids = np.arange(100100, dtype=np.int64)
        labels = (ids % 100).astype(np.int16)
        manifest = {"prefix_100k_ordered_base_ids_int64_le_sha256": hashlib.sha256(ids[:100000].astype("<i8").tobytes()).hexdigest(),
                    "prefix_100k_radial_labels_int16_le_sha256": hashlib.sha256(labels[:100000].astype("<i2").tobytes()).hexdigest()}
        verify.verify_prefix_hashes(manifest, ids, labels)
        labels[-1] = 0
        verify.verify_prefix_hashes(manifest, ids, labels)
        for name in manifest:
            with self.subTest(field=name), self.assertRaises(AssertionError):
                verify.verify_prefix_hashes({**manifest, name: "wrong"}, ids, labels)
            with self.assertRaises(AssertionError):
                verify.verify_prefix_hashes({k: v for k, v in manifest.items() if k != name}, ids, labels)
        with self.assertRaises(AssertionError):
            verify.verify_prefix_hashes(manifest, ids[:100], labels[:100])

    def test_source_neighborhoods_distances_anchor_counts_and_grid_recomputed(self):
        ids, vectors, anchor = synthetic_vectors()
        radial, _ = metadata.build_metadata(ids, vectors, anchor)
        labels = {"legacy": (np.arange(1000) % 100).astype(np.int16), "radial": radial}
        queries = {9: anchor, 3: vectors[25]}
        records = metadata.neighborhoods(ids, vectors, queries, **labels, anchor=anchor)
        verify.verify_neighbors(records, ids, vectors, queries, labels, anchor)
        for corrupt in ("ids", "distance", "anchor", "count", "grid", "order"):
            changed = copy.deepcopy(records)
            if corrupt == "ids":
                changed[0]["neighbor_ids"][0:2] = reversed(changed[0]["neighbor_ids"][0:2])
            elif corrupt == "distance":
                changed[0]["squared_distances"][0] += 1
            elif corrupt == "anchor":
                changed[0]["query_anchor_distance"] += 1
            elif corrupt == "count":
                changed[0]["local_counts"]["radial"]["5"]["40"] += 1
            elif corrupt == "grid":
                changed.pop()
            else:
                changed.reverse()
            with self.subTest(corrupt=corrupt), self.assertRaises(AssertionError):
                verify.verify_neighbors(changed, ids, vectors, queries, labels, anchor)


class ScheduleProvenanceTests(unittest.TestCase):
    def fixture(self):
        config = stage_config(100000, 1)
        frozen = {"modes": list(MODES), "blocks": [{"block_index": 1, "method": "exact", "filter_threshold": 1,
                  "query_order_by_repetition": [[7, 8]] * 5}]}
        rows = []
        for mode in MODES:
            for phase, repetition, ids in [("disjoint_warmup", 0, [9])] + [("measured", r, [7, 8]) for r in range(1, 6)]:
                for query in ids:
                    rows.append({"scale_rows": 100000, "build_number": 1, "metadata_mode": mode, "block_index": 1,
                                 "method": "exact", "filter_threshold": 1, "phase": phase, "repetition": repetition,
                                 "query_id": query, "sequence_index": len(rows) + 1})
        return config, frozen, [r for r in rows if r["phase"] == "measured"], [r for r in rows if r["phase"] != "measured"]

    def test_complete_schedule_and_mode_order(self):
        config, frozen, measured, prepared = self.fixture()
        verify.verify_schedule_rows(measured, prepared, frozen, config, [7, 8], [9])
        frozen["modes"].reverse()
        with self.assertRaisesRegex(AssertionError, "mode order"):
            verify.verify_schedule_rows(measured, prepared, frozen, config, [7, 8], [9])

    def test_missing_duplicate_wrong_scale_query_mode_and_phase_rejected(self):
        for field, value in (("scale_rows", 250000), ("metadata_mode", "other"), ("query_id", 9),
                             ("sequence_index", 1), ("phase", "disjoint_warmup"), ("repetition", 0)):
            config, frozen, measured, prepared = self.fixture()
            measured[0][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                verify.verify_schedule_rows(measured, prepared, frozen, config, [7, 8], [9])
        config, frozen, measured, prepared = self.fixture()
        with self.assertRaises(AssertionError):
            verify.verify_schedule_rows(measured[:-1], prepared, frozen, config, [7, 8], [9])

    def test_prepared_counts_mode_and_single_vector_sql(self):
        for mode in MODES:
            original = prepared_fixture(mode)
            verify.verify_prepared(original, mode)
            for field, value in (("generic_plans", 1021), ("custom_plans", 1), ("parameter_types", "{vector,vector}"),
                                 ("statement", db.search_sql("exact", "radial" if mode == "legacy" else "legacy", 50).replace("%s", "$1"))):
                changed = copy.deepcopy(original)
                changed["exact"][0][field] = value
                with self.subTest(field=field), self.assertRaises(AssertionError):
                    verify.verify_prepared(changed, mode)

    def test_sql_clock_schema_and_source_provenance(self):
        config = stage_config(100000, 1)
        row = {"schema_version": 1, "run_id": "run", "config_sha256": "digest", "scale_rows": 100000,
               "build_number": 1, "k": 10, "prepared": True, "backend_pid": 123, "plan_audit_id": "plan",
               "method": "exact", "metadata_mode": "radial", "filter_threshold": 1,
               "sql_sha256": hashlib.sha256(db.search_sql("exact", "radial", 1).encode()).hexdigest(),
               "error_type": None, "error_message": None, "timeout": False, "duration_ns": 10, "start_monotonic_ns": 100}
        verify.verify_row_provenance(row, "run", "digest", config, 123, "plan")
        for field, value in (("schema_version", True), ("scale_rows", 250000), ("build_number", 2),
                             ("sql_sha256", "wrong"), ("timeout", True), ("error_message", "failure"),
                             ("duration_ns", 0), ("duration_ns", True), ("start_monotonic_ns", -1)):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                verify.verify_row_provenance({**row, field: value}, "run", "digest", config, 123, "plan")

    def test_six_concurrency_boundaries_include_load_and_reject_extra_clients(self):
        sessions = {mode: {"backend_pids": dict(zip(METHODS, (101, 102, 103)))} for mode in MODES}
        checks = [{"phase": p, "allowed_method_pids": [], "other_clients": []} for p in ("stage_start", "load")]
        for mode in MODES:
            checks.extend([{"phase": f"{mode}_reset", "allowed_method_pids": [], "other_clients": []},
                           {"phase": f"{mode}_end", "allowed_method_pids": [101, 102, 103],
                            "other_clients": [{"pid": pid} for pid in (101, 102, 103)]}])
        evidence = {"advisory_lock_key": 73120412026, "lock_held_until_stage_end": True, "checks": checks}
        verify.verify_concurrency(evidence, {"modes": list(MODES)}, sessions)
        for corruption in ("missing_load", "extra_client", "missing_client", "wrong_order"):
            changed = copy.deepcopy(evidence)
            if corruption == "missing_load":
                changed["checks"].pop(1)
            elif corruption == "extra_client":
                changed["checks"][1]["other_clients"] = [{"pid": 999}]
            elif corruption == "missing_client":
                changed["checks"][3]["other_clients"].pop()
            else:
                changed["checks"].reverse()
            with self.subTest(corruption=corruption), self.assertRaises(AssertionError):
                verify.verify_concurrency(changed, {"modes": list(MODES)}, sessions)


class TruthVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ids, vectors, anchor = synthetic_vectors()
        buckets = np.arange(1000) % 100
        queries = {q: anchor for q in range(200)}
        records = []
        for query in queries:
            for threshold in FILTERS:
                chosen = np.flatnonzero(buckets < threshold)
                distances = np.sqrt(np.sum(vectors[chosen].astype(np.float64) ** 2, axis=1))
                order = np.lexsort((ids[chosen], distances))
                boundary = distances[order[9]]
                rows = [(int(ids[chosen[p]]), float(distances[p])) for p in order if distances[p] <= boundary]
                records.append(db.make_truth_record(mode="legacy", metadata_sha256="metadata", run_id="run", scale_rows=1000,
                                                     threshold=threshold, qualifying_count=10 * threshold, query_id=query,
                                                     k=10, rows=rows, dataset_sha256="dataset"))
        truth = verify.ground_truth_index(records)
        independent = validate_ground_truth_numpy(records=truth, validation_keys=select_validation_keys(queries, FILTERS, 20),
                                                  base_ids=ids, vectors=vectors, buckets=buckets, query_vectors=queries, k=10)
        cls.records = records
        cls.arguments = dict(mode="legacy", metadata_sha="metadata", config={"scale_rows": 1000}, run_id="run", dataset_sha="dataset",
                             base_ids=ids, buckets=buckets, vectors=vectors, queries=queries, measured_ids=list(queries),
                             reexecution={"passed": True, "metadata_mode": "legacy", "reexecuted_records": 1000,
                                          "record_checksums_identical_in_order": True, "duration_ns": 1}, independent=independent)

    def test_complete_truth_grid_and_source_distance_checks(self):
        self.assertEqual(len(verify.verify_truth(self.records, **self.arguments)), 1000)

    def test_missing_duplicate_wrong_provenance_and_rehashed_false_partition_rejected(self):
        for corruption in ("missing", "duplicate", "mode", "sql", "tie", "distance"):
            records = copy.deepcopy(self.records)
            if corruption == "missing":
                records.pop()
            elif corruption == "duplicate":
                records.append(records[0])
            else:
                record = records[0]
                if corruption == "mode":
                    record["metadata_mode"] = "radial"
                elif corruption == "sql":
                    record["generation_sql"] = db.ground_truth_sql("radial", 50)
                elif corruption == "tie":
                    record["strictly_closer_ids"] = []
                else:
                    record["all_with_ties_distances"][0] += 0.125
                    record["canonical_distances"][0] += 0.125
                rehash(record)
            with self.subTest(corruption=corruption), self.assertRaises((AssertionError, ValueError)):
                verify.verify_truth(records, **self.arguments)

    def test_reexecution_and_fresh_numpy_validation_cannot_be_omitted(self):
        for field, value in (("reexecution", {"passed": True}), ("independent", {"passed": True})):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                verify.verify_truth(self.records, **{**self.arguments, field: value})


class PhysicalAndSourceTests(unittest.TestCase):
    def test_physical_rows_filter_proportions_dimension_indexes_and_hashes(self):
        original = physical_evidence()
        verify.verify_database(original, 100000, "source", physical_identity())
        for field, value in (("scale_rows", 250000), ("exact_count", 99999), ("hnsw_vector_stream_sha256", "wrong"),
                             ("dimensions", {"minimum": 127, "maximum": 128}), ("filter_counts", {}),
                             ("statistics", []), ("nonfinite_vector_counts", {"exact": 0, "hnsw": 1})):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                verify.verify_database({**original, field: value}, 100000, "source", physical_identity())
        for corruption in ("index", "settings", "size"):
            changed = copy.deepcopy(original)
            if corruption == "index":
                changed["indexes"][2]["definition"] = "USING btree (radial_bucket)"
            elif corruption == "settings":
                changed["indexes"][-1]["definition"] = changed["indexes"][-1]["definition"].replace("m='16'", "m='32'")
            else:
                changed["relation_sizes"][0]["relation_bytes"] = 0
            with self.subTest(corruption=corruption), self.assertRaises(AssertionError):
                verify.verify_database(changed, 100000, "source", physical_identity())

    def test_schema_seven_relations_unique_oids_and_filenodes(self):
        original = physical_identity()
        self.assertEqual(set(verify.validate_identity(original)), set(db.RELATIONS))
        for field in ("oid", "filenode", "relation", "kind"):
            changed = copy.deepcopy(original)
            changed["relations"][0][field] = changed["relations"][1][field]
            if field == "kind":
                changed["relations"][0][field] = "i"
            with self.subTest(field=field), self.assertRaises(AssertionError):
                verify.validate_identity(changed)
        with self.assertRaises(AssertionError):
            verify.validate_identity({**original, "schema": "milestone2"})

    def test_recorded_commit_inventory_and_current_shared_helpers_are_bound(self):
        config = stage_config(100000, 1)
        blobs = {config["source_protocol"]: b'{"dataset":"fixture"}',
                 "config/metadata-association-v1.json": json.dumps({k: v for k, v in config.items() if k not in ("scale_rows", "build_number")}).encode(),
                 "experiments/association/protocol.py": b"protocol", "experiments/association/verify.py": b"verify",
                 "experiments/milestone2/metrics.py": b"metric implementation"}
        commit = "a" * 40
        manifest = {"git_at_start": {"commit": commit, "dirty": False, "status_porcelain": []},
                    "expected_source_commit": commit, "source_protocol": {"dataset": "fixture"},
                    "source_file_sha256": {name: hashlib.sha256(body).hexdigest() for name, body in blobs.items()}}

        def git(command, **kwargs):
            self.assertIn(commit, command[2] if command[1] == "show" else command)
            return SimpleNamespace(stdout=blobs[command[2].split(":", 1)[1]] if command[1] == "show" else "\n".join(blobs))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in blobs.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(body)
            with patch.object(verify, "ROOT", root), patch.object(verify.subprocess, "run", side_effect=git):
                self.assertEqual(verify.verify_source_commit(manifest, config), {"dataset": "fixture"})
                for field, value in (("expected_source_commit", "b" * 40), ("source_file_sha256", {})):
                    with self.subTest(field=field), self.assertRaises(AssertionError):
                        verify.verify_source_commit({**manifest, field: value}, config)
                (root / "experiments/milestone2/metrics.py").write_bytes(b"changed implementation")
                with self.assertRaisesRegex(AssertionError, "verification source differs"):
                    verify.verify_source_commit(manifest, config)

    def test_predecessor_stage_fresh_physical_graph_and_100k_prefix_must_match(self):
        old_config, config = stage_config(100000, 1), stage_config(250000, 1)
        old_manifest = {"source_file_sha256": {"file": "hash"}, "git_at_start": {"commit": "source"}}
        metadata_manifest = {"prefix_100k_ordered_base_ids_int64_le_sha256": "ids", "prefix_100k_radial_labels_int16_le_sha256": "labels"}
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory)
            write_json(previous, "config.json", old_config)
            write_json(previous, "manifest.json", old_manifest)
            write_json(previous, "COMPLETE.json", {"valid": True, "run_id": previous.name, "config_sha256": sha256_json(old_config),
                                                   "research_conclusion_authorized": False})
            write_json(previous, "identity.json", physical_identity())
            write_json(previous, "metadata_manifest.json", metadata_manifest)
            manifest = {**old_manifest, "predecessor": {"run_directory": str(previous), "verification": {
                "passed": True, "run_id": previous.name, "config_sha256": sha256_json(old_config), "source_commit": "source"}}}
            with patch.object(verify, "verify_manifest", return_value={}):
                verify.verify_predecessor(manifest, config, physical_identity(100), metadata_manifest)
                for identity, metadata_value in ((physical_identity(), metadata_manifest),
                                                  (physical_identity(100), {**metadata_manifest, "prefix_100k_radial_labels_int16_le_sha256": "changed"})):
                    with self.subTest(), self.assertRaises(AssertionError):
                        verify.verify_predecessor(manifest, config, identity, metadata_value)
                with self.assertRaisesRegex(AssertionError, "previous frozen stage"):
                    verify.verify_predecessor(manifest, stage_config(250000, 2), physical_identity(100), metadata_manifest)
                with self.assertRaises(AssertionError):
                    verify.verify_predecessor(manifest, old_config, physical_identity(100), metadata_manifest)
        verify.verify_predecessor({"predecessor": None}, old_config, physical_identity(), metadata_manifest)

    def test_real_plan_documents_are_revalidated_not_just_passed_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity, mode, config = physical_identity(), "radial", stage_config(100000, 1)
            sessions = {"backend_pids": dict(zip(METHODS, (101, 102, 103))),
                        "settings": {m: {**settings(m), **SESSION_CONTROLS, "work_mem": "4MB" if m == "exact" else "64MB"}
                                     for m in METHODS}}
            for suffix in ("identity_before.json", "identity_after.json"):
                write_json(root, f"{mode}_{suffix}", identity)
            write_json(root, f"{mode}_cache_reset.json", {"operating_system_cache_flushed": False, "postmaster_restarted": False,
                       "method": "pg_buffercache_evict over a materialized buffer-id snapshot after CHECKPOINT", "after": {"buffers_used": 0}})
            write_json(root, f"{mode}_method_sessions.json", sessions)
            write_json(root, f"{mode}_method_sessions_after.json", {**sessions, "server_controls": SERVER_CONTROLS})
            prepared = prepared_fixture(mode)
            write_json(root, f"{mode}_prepared_statements.json", prepared)
            plans = []
            for method in METHODS:
                for threshold in FILTERS:
                    plan_id = hashlib.sha256(f"association-plan-v1|100000|{method}|{mode}|{threshold}|999".encode()).hexdigest()[:20]
                    path = f"plans/{mode}_{plan_id}.json"
                    document = json.loads(json.dumps(exact_plan() if method == "exact" else ann_plan(count=10)).replace("radial_bucket < 5)", f"radial_bucket < {threshold})"))
                    write_json(root, path, document)
                    assertions = db.verify_plan_document(method=method, mode=mode, threshold=threshold, document=document,
                                                         observed_settings=sessions["settings"][method], fetched_result_count=10)
                    self.assertTrue(assertions["passed"], assertions)
                    plans.append({**assertions, "method": method, "filter_threshold": threshold, "plan_id": plan_id,
                                  "build_number": 1, "metadata_mode": mode, "scale_rows": 100000, "raw_plan_path": path,
                                  "query_id": 999, "backend_pid": sessions["backend_pids"][method],
                                  "expected_index": None if method == "exact" else db.HNSW_INDEX,
                                  "plan_capture": "EXPLAIN ANALYZE VERBOSE EXECUTE of the workload prepared generic statement",
                                  "prepared_statement": {"name": f"statement_{threshold}",
                                    "statement": db.search_sql(method, mode, threshold).replace("%s", "$1"), "parameter_types": "{vector}",
                                    "generic_plans_before_explain": 1, "generic_plans_after_explain": 2,
                                    "custom_plans_before_explain": 0, "custom_plans_after_explain": 0},
                                  "fetched_result_ids": list(range(10)), "fetched_result_distances": list(map(float, range(10)))})
            path = root / f"{mode}_plan_assertions.jsonl"
            path.write_text("".join(json.dumps(p) + "\n" for p in plans))
            self.assertEqual(len(verify.verify_mode(root, mode, config, identity, 999)[1]), 15)
            target = root / plans[-1]["raw_plan_path"]
            changed = json.loads(target.read_text())
            changed[0]["Plan"]["Plans"][0]["Schema"] = "milestone2"
            target.write_text(json.dumps(changed))
            with self.assertRaisesRegex(AssertionError, "raw plan validation"):
                verify.verify_mode(root, mode, config, identity, 999)


class ResultAndResourceTests(unittest.TestCase):
    def test_recall_fixed_denominator_ties_completeness_and_distances(self):
        truth = {"canonical_ids": list(range(10)), "strictly_closer_ids": [0, 1],
                 "boundary_tie_ids": list(range(2, 12)), "record_sha256": "truth"}
        row = {"result_ids": [0, 10], "distances": [0.0, 10.0], "filter_threshold": 5, "method": "hnsw_standard",
               "returned_count": 2, "returned_k": False, "shortfall": 8, "ids_unique": True, "scale_valid": True,
               "filter_valid": True, "distance_order_valid": True, "canonical_recall_at_10": 0.1,
               "tie_aware_recall_at_10": 0.2, "ground_truth_record_sha256": "truth"}
        buckets = {i: 0 for i in range(12)}
        verify.validate_results(row, buckets, truth)
        for field, value in (("canonical_recall_at_10", 0.5), ("tie_aware_recall_at_10", 1.0), ("returned_k", True),
                             ("shortfall", 0), ("ground_truth_record_sha256", "other"), ("method", "exact")):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                verify.validate_results({**row, field: value}, buckets, truth)
        values = np.zeros((12, 128), dtype=np.float32)
        values[:, 0] = np.arange(12)
        verify.verify_distances(row, values, dict(enumerate(range(12))), values[0])
        with self.assertRaisesRegex(AssertionError, "L2"):
            verify.verify_distances({**row, "distances": [0.0, 10.1]}, values, dict(enumerate(range(12))), values[0])

    def test_resource_snapshots_cover_all_durable_passes(self):
        rows = [{"sequence_index": i, "metadata_mode": "legacy", "block_index": 1, "phase": "measured", "repetition": 1}
                for i in range(1, 181)]
        chunks = [{"last_sequence_index": i} for i in range(1, 181)]
        snapshots = [{"after_sequence_index": r["sequence_index"], "host": {"memory_available_bytes": 1},
                      **{k: r[k] for k in ("metadata_mode", "block_index", "phase", "repetition")}} for r in rows]
        verify.verify_resources(snapshots, chunks, rows)
        for corrupt in ("missing", "sequence", "host"):
            changed = copy.deepcopy(snapshots)
            if corrupt == "missing":
                changed.pop()
            elif corrupt == "sequence":
                changed[0]["after_sequence_index"] = 2
            else:
                changed[0]["host"] = {}
            with self.subTest(corrupt=corrupt), self.assertRaises(AssertionError):
                verify.verify_resources(changed, chunks, rows)


if __name__ == "__main__":
    unittest.main()
