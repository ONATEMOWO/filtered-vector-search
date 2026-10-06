"""Focused adapter contracts; these tests do not contact PostgreSQL."""

from __future__ import annotations

import copy
import hashlib
import unittest
import numpy as np

from experiments.association import database as db
from experiments.milestone2.config import canonical_json_bytes
from experiments.milestone2.ground_truth import ground_truth_index


def settings(method="hnsw_standard"):
    common = {"jit": "off", "plan_cache_mode": "force_generic_plan", "statement_timeout": "2min"}
    if method == "exact":
        return {**common, **{key: "on" for key in ("enable_seqscan", "enable_bitmapscan", "enable_indexscan", "enable_indexonlyscan")}}
    return {**common, "hnsw.ef_search": "40", "hnsw.iterative_scan": "off" if method == "hnsw_standard" else "strict_order",
            "hnsw.max_scan_tuples": "20000", "hnsw.scan_mem_multiplier": "1", "work_mem": "64MB",
            "enable_seqscan": "off", "enable_bitmapscan": "off"}


def ann_plan(mode="radial", count=3):
    scan = {"Node Type": "Index Scan", "Index Name": db.HNSW_INDEX, "Relation Name": "sift_hnsw", "Schema": "association",
            "Order By": "(sift_hnsw.embedding <-> $1)", "Filter": f"(sift_hnsw.{db.column_for(mode)} < 5)",
            "Actual Rows": count, "Actual Loops": 1, "Rows Removed by Filter": 37}
    return [{"Plan": {"Node Type": "Limit", "Actual Rows": count, "Actual Loops": 1, "Plans": [scan]}}]


def exact_plan():
    scan = {"Node Type": "Seq Scan", "Relation Name": "sift_exact", "Schema": "association",
            "Filter": "(sift_exact.radial_bucket < 5)", "Actual Rows": 5000, "Actual Loops": 1}
    sort = {"Node Type": "Sort", "Sort Key": ["((sift_exact.embedding <-> $1))", "sift_exact.id"],
            "Actual Rows": 10, "Actual Loops": 1, "Plans": [scan]}
    return [{"Plan": {"Node Type": "Limit", "Actual Rows": 10, "Actual Loops": 1, "Plans": [sort]}}]


class SqlTests(unittest.TestCase):
    def test_single_bound_vector_and_whitelisted_columns(self):
        for method in db.METHODS:
            for mode in db.MODE_COLUMNS:
                for threshold in db.FILTERS:
                    statement = db.search_sql(method, mode, threshold)
                    self.assertEqual(statement.count("%s"), 1)
                    self.assertIn(f"WHERE {db.column_for(mode)} < {threshold}", statement)
                    self.assertIn(db.EXACT_TABLE if method == "exact" else db.HNSW_TABLE, statement)
                    self.assertIn("ORDER BY distance, id" if method == "exact" else "ORDER BY distance LIMIT", statement)

    def test_unknown_identifiers_and_nonprotocol_values_rejected(self):
        for args in (("exact", "radial; DROP TABLE x", 5), ("wrong", "radial", 5),
                     ("exact", "radial", True), ("exact", "radial", 25)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                db.search_sql(*args)
        with self.assertRaises(ValueError):
            db.search_sql("exact", "radial", 5, k=11)

    def test_ground_truth_uses_with_ties_and_mode_specific_exact_predicate(self):
        statement = db.ground_truth_sql("radial", 1)
        self.assertIn(db.EXACT_TABLE, statement)
        self.assertIn("WHERE radial_bucket < 1", statement)
        self.assertIn("FETCH FIRST 10 ROWS WITH TIES", statement)
        self.assertNotIn("ORDER BY distance, id", statement)
        self.assertEqual(statement.count("%s"), 1)


class PlanTests(unittest.TestCase):
    def check(self, document, *, method="hnsw_standard", mode="radial", count=3, observed=None):
        return db.verify_plan_document(method=method, mode=mode, threshold=5, document=document,
                                       observed_settings=observed or settings(method), fetched_result_count=count)

    def test_valid_ann_shortfall_and_empty_results_remain_valid(self):
        for count in (0, 3, 10):
            result = self.check(ann_plan(count=count), count=count)
            self.assertTrue(result["passed"], result["failures"])
            self.assertEqual(result["actual_rows"], count)
        self.assertTrue(self.check(ann_plan(), method="hnsw_iterative")["passed"])

    def test_exact_realistic_sequential_plan_passes(self):
        self.assertTrue(self.check(exact_plan(), method="exact", count=10)["passed"])

    def test_wrong_mode_schema_index_order_and_counts_rejected(self):
        mutations = (("Filter", "(filter_bucket < 5)"), ("Filter", "(radial_bucket < 50)"),
                     ("Schema", "milestone2"), ("Relation Name", "sift_exact"),
                     ("Index Name", "sift_hnsw_pkey"), ("Order By", "embedding <-> $2"),
                     ("Actual Loops", 0), ("Actual Rows", 4))
        for key, value in mutations:
            document = ann_plan()
            document[0]["Plan"]["Plans"][0][key] = value
            with self.subTest(key=key, value=value):
                self.assertFalse(self.check(document)["passed"])

    def test_extra_sort_or_scan_cannot_disguise_ann_path(self):
        document = ann_plan()
        root = document[0]["Plan"]
        root["Plans"] = [{"Node Type": "Sort", "Sort Key": ["embedding <-> $1"], "Plans": root["Plans"]}]
        self.assertFalse(self.check(document)["passed"])
        document = ann_plan()
        document[0]["Plan"]["Plans"].append(copy.deepcopy(document[0]["Plan"]["Plans"][0]))
        self.assertFalse(self.check(document)["passed"])

    def test_wrong_settings_fetched_count_and_incomplete_exact_rejected(self):
        observed = settings()
        observed["hnsw.iterative_scan"] = "strict_order"
        self.assertFalse(self.check(ann_plan(), observed=observed)["passed"])
        self.assertFalse(self.check(ann_plan(), count=2)["passed"])
        document = exact_plan()
        document[0]["Plan"]["Actual Rows"] = 9
        self.assertFalse(self.check(document, method="exact", count=9)["passed"])


class TruthTests(unittest.TestCase):
    def record(self, mode="radial", metadata="m" * 64):
        return db.make_truth_record(mode=mode, metadata_sha256=metadata, run_id="run", scale_rows=100000,
                                    threshold=5, qualifying_count=5000, query_id=7, k=10,
                                    rows=[(i, float(i)) for i in range(10)], dataset_sha256="d" * 64)

    def test_mode_and_assignment_are_in_truth_checksum(self):
        radial, legacy = self.record(), self.record("legacy")
        self.assertNotEqual(radial["record_sha256"], legacy["record_sha256"])
        self.assertNotEqual(radial["record_sha256"], self.record(metadata="n" * 64)["record_sha256"])
        self.assertEqual(radial["metadata_mode"], "radial")
        self.assertEqual(radial["metadata_sha256"], radial["scale_manifest_sha256"])
        self.assertEqual(radial["generation_sql"], db.ground_truth_sql("radial", 5))
        self.assertIn((7, 5), ground_truth_index([radial]))
        body = {k: v for k, v in radial.items() if k != "record_sha256"}
        self.assertEqual(hashlib.sha256(canonical_json_bytes(body)).hexdigest(), radial["record_sha256"])

    def test_modified_mode_without_rehash_rejected_by_existing_truth_validator(self):
        record = self.record()
        record["metadata_mode"] = "legacy"
        with self.assertRaisesRegex(ValueError, "checksum"):
            ground_truth_index([record])


class FakeCopy:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def write_row(self, row):
        self.cursor.rows.append(row)


class FakeCursor:
    def __init__(self):
        self.events, self.rows = [], []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, statement, parameters=(), *, prepare=False):
        self.events.append((statement, parameters, prepare))

    def copy(self, statement):
        self.events.append((statement, (), False))
        return FakeCopy(self)

    def fetchone(self):
        return ("1GB", "0")


class FakeConnection:
    def __init__(self):
        self.handle = FakeCursor()

    def cursor(self):
        return self.handle


class LoadingTests(unittest.TestCase):
    def arrays(self):
        return {"base_ids": np.arange(100, dtype=np.int32), "vectors": np.ones((100, 128), dtype=np.float32),
                "legacy": np.arange(100, dtype=np.int16), "radial": np.arange(99, -1, -1, dtype=np.int16)}

    def test_both_metadata_columns_loaded_before_single_graph_is_built(self):
        connection = FakeConnection()
        phases = db.load_scale(connection, **self.arrays())
        statements = [event[0] for event in connection.handle.events]
        copy_at = next(i for i, s in enumerate(statements) if s.startswith("COPY "))
        ann_at = next(i for i, s in enumerate(statements) if s.startswith("INSERT INTO "))
        graph_at = next(i for i, s in enumerate(statements) if "USING hnsw" in s)
        self.assertLess(copy_at, ann_at)
        self.assertLess(ann_at, graph_at)
        self.assertIn("filter_bucket, radial_bucket, embedding", statements[copy_at])
        self.assertIn("filter_bucket, radial_bucket, embedding", statements[ann_at])
        self.assertEqual(len(connection.handle.rows), 100)
        self.assertEqual(connection.handle.rows[0][:4], (0, 0, 0, 99))
        self.assertEqual(sum("USING hnsw" in s for s in statements), 1)
        self.assertEqual(sum("USING btree" in s for s in statements), 2)
        self.assertFalse(any("UPDATE " in s for s in statements))
        self.assertTrue(all("association." in s for s in statements if s.startswith("DROP TABLE")))
        self.assertEqual(phases["hnsw_build_settings"], {**db.BUILD_SETTINGS, "m": 16, "ef_construction": 64})

    def test_invalid_assignment_rejected_before_database_mutation(self):
        arguments = self.arrays()
        arguments["radial"][:] = 0
        connection = FakeConnection()
        with self.assertRaises(ValueError):
            db.load_scale(connection, **arguments)
        self.assertEqual(connection.handle.events, [])

    def test_checksum_binds_both_columns_vectors_ids_and_order(self):
        arguments = self.arrays()
        original = db.source_stream_checksum(**arguments)
        for key in arguments:
            changed = {name: value.copy() for name, value in arguments.items()}
            changed[key][0] += 1
            with self.subTest(key=key):
                self.assertNotEqual(original, db.source_stream_checksum(**changed))


if __name__ == "__main__":
    unittest.main()
