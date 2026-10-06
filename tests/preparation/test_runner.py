from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from experiments.milestone2.database import search_sql
from experiments.milestone2.restart import EXPECTED_RELATIONS
from experiments.preparation import runner
from experiments.preparation.protocol import FILTERS, METHODS, PROTOCOL


class Cursor:
    def __init__(self, rows=(), one=None):
        self.rows, self.one, self.executions = list(rows), one, []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql, parameters=(), *, prepare=False):
        self.executions.append((sql, parameters, prepare))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


class Connection:
    def __init__(self, cursor):
        self.value = cursor

    def cursor(self):
        return self.value


def identity(offset=0):
    return {"postmaster_started_at": "2026-10-06T12:00:00+00:00", "system_identifier": "123",
            "database": "filtered_vector_search", "server_version_num": "170011",
            "relations": [{"relation": name, "kind": kind, "oid": 100 + offset + i,
                           "filenode": 1000 + offset + i}
                          for i, (name, kind) in enumerate(EXPECTED_RELATIONS.items())]}


def prepared(arm):
    return {method: [{"statement": search_sql(method, threshold, 10).replace("%s", "$1"),
                      "generic_plans": 1022 if arm == "A" else 1222, "custom_plans": 0,
                      "parameter_types": "{vector}", "name": f"stmt_{threshold}"}
                     for threshold in FILTERS] for method in METHODS}


class IsolationTests(unittest.TestCase):
    def test_advisory_lock_must_be_obtained(self):
        runner.acquire_campaign_lock(Connection(Cursor(one=(True,))))
        with self.assertRaisesRegex(RuntimeError, "advisory lock"):
            runner.acquire_campaign_lock(Connection(Cursor(one=(False,))))

    def test_other_clients_across_databases_are_rejected(self):
        connection = Connection(Cursor(rows=[(42, "otherdb", "psql", "idle")]))
        with self.assertRaisesRegex(RuntimeError, "other client"):
            runner.guard_other_clients(connection)
        self.assertEqual(len(runner.guard_other_clients(connection, [42])), 1)
        self.assertEqual(runner.guard_other_clients(Connection(Cursor())), [])

    def test_pair_same_physical_graph_and_server_required(self):
        runner.assert_same_arm_identity(identity(), identity())
        with self.assertRaises(AssertionError):
            runner.assert_same_arm_identity(identity(), identity(100))
        later = identity()
        later["postmaster_started_at"] = "2026-10-06T13:00:00+00:00"
        with self.assertRaisesRegex(AssertionError, "restarted"):
            runner.assert_same_arm_identity(identity(), later)

    def test_second_build_requires_new_objects_same_cluster(self):
        runner.assert_distinct_builds(identity(), identity(100))
        with self.assertRaisesRegex(AssertionError, "reused"):
            runner.assert_distinct_builds(identity(), identity())
        other = identity(100)
        other["database"] = "wrong_database"
        with self.assertRaisesRegex(AssertionError, "cluster"):
            runner.assert_distinct_builds(identity(), other)


class PreparedCountsTests(unittest.TestCase):
    def test_method_settings_boundaries_must_match_without_reconfiguration(self):
        connections = {method: object() for method in METHODS}
        with patch.object(runner, "session_settings", return_value={"work_mem": "4MB"}) as legacy, \
             patch.object(runner, "read_settings", return_value={"max_parallel_workers": "8"}) as controls:
            observed = runner.capture_method_settings(connections)
        self.assertEqual(legacy.call_count, 3)
        self.assertEqual(controls.call_count, 3)
        runner.assert_unchanged_settings(observed, observed)
        changed = {**observed, "exact": {**observed["exact"], "work_mem": "8MB"}}
        with self.assertRaisesRegex(AssertionError, "settings changed"):
            runner.assert_unchanged_settings(observed, changed)

    def test_exact_generic_execution_budget_both_arms(self):
        for arm in ("A", "B"):
            runner.assert_prepared_counts(prepared(arm), arm)

    def test_counter_parameter_and_matrix_tampering_rejected(self):
        for field, value in (("generic_plans", 1021), ("custom_plans", 1), ("parameter_types", "{vector,vector}")):
            with self.subTest(field=field):
                evidence = prepared("A")
                evidence["exact"][0][field] = value
                with self.assertRaises(AssertionError):
                    runner.assert_prepared_counts(evidence, "A")
        evidence = prepared("A")
        evidence["exact"].pop()
        with self.assertRaises(AssertionError):
            runner.assert_prepared_counts(evidence, "A")
        with self.assertRaises(AssertionError):
            runner.assert_prepared_counts(prepared("A"), "C")


class ObservationTests(unittest.TestCase):
    def row(self, phase="measured", method="exact", rows=None):
        ids = list(range(10))
        truth = {"canonical_ids": ids, "strictly_closer_ids": ids[:9], "boundary_tie_ids": [9], "record_sha256": "a" * 64}
        cursor = Cursor(rows=[(i, float(i)) for i in ids] if rows is None else rows)
        result = runner.observation(cursor=cursor, vector=np.zeros(128, dtype=np.float32),
                                    base={"method": method, "filter_threshold": 50, "phase": phase},
                                    sequence_index=1, selected_buckets={i: 0 for i in ids},
                                    truth=None if phase == "disjoint_warmup" else truth)
        return result, cursor

    def test_measured_and_exposure_scored_against_exact_truth(self):
        for phase in ("measured", "measured_exposure"):
            row, cursor = self.row(phase)
            runner.assert_valid_row(row)
            self.assertEqual(row["canonical_recall_at_10"], 1)
            self.assertEqual(row["tie_aware_recall_at_10"], 1)
            self.assertTrue(row["prepared"])
            self.assertEqual(len(cursor.executions[0][1]), 1)
            self.assertTrue(cursor.executions[0][2])
            self.assertGreater(row["duration_ns"], 0)

    def test_disjoint_warmup_has_no_false_ground_truth_claim(self):
        row, _ = self.row("disjoint_warmup")
        runner.assert_valid_row(row)
        self.assertIsNone(row["canonical_recall_at_10"])
        self.assertIsNone(row["ground_truth_record_sha256"])

    def test_approximate_incompleteness_preserved_not_rejected(self):
        row, _ = self.row(method="hnsw_standard", rows=[])
        runner.assert_valid_row(row)
        self.assertFalse(row["returned_k"])
        self.assertEqual(row["canonical_recall_at_10"], 0)
        exact, _ = self.row(rows=[])
        with self.assertRaises(AssertionError):
            runner.assert_valid_row(exact)

    def test_query_error_is_not_mistaken_for_valid_empty_approximation(self):
        row, _ = self.row(method="hnsw_standard", rows=[])
        row["error_type"] = "QueryCanceled"
        with self.assertRaisesRegex(AssertionError, "query failed|query|Query"):
            runner.assert_valid_row(row)


class FailurePreservationTests(unittest.TestCase):
    def test_dirty_source_fails_before_run_creation(self):
        with patch.object(runner, "load_protocol", return_value=PROTOCOL), \
             patch.object(runner, "git_state", return_value={"dirty": True}), \
             patch.object(runner, "create_run") as create:
            with self.assertRaisesRegex(RuntimeError, "clean committed"):
                runner.run_campaign(Path("irrelevant"), Path("irrelevant"))
            create.assert_not_called()

    def test_source_validation_failure_is_immutable_invalid_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(runner, "RUNS_ROOT", root), \
                 patch.object(runner, "load_protocol", return_value=PROTOCOL), \
                 patch.object(runner, "git_state", return_value={"dirty": False, "status_porcelain": [], "commit": "a" * 40}), \
                 patch.object(runner, "source_identity", return_value={"file": "hash"}), \
                 patch.object(runner, "verify_milestone1_preserved", return_value={"preserved": True}), \
                 patch.object(runner, "energy_mode", return_value={"ac_power_detected": True}), \
                 patch.object(runner, "validate_hdf5", side_effect=AssertionError("bad source checksum")):
                with self.assertRaisesRegex(AssertionError, "bad source"):
                    runner.run_campaign(Path("ignored"), Path("missing"))
            run = next(root.iterdir())
            self.assertTrue((run / "INVALID.json").is_file())
            self.assertTrue((run / "checksums.sha256").is_file())
            self.assertFalse((run / "COMPLETE.json").exists())
            self.assertFalse((run / "ACTIVE").exists())
            self.assertEqual(json.loads((run / "failure.json").read_text())["phase"], "source_validation")


if __name__ == "__main__":
    unittest.main()
