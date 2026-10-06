"""Runner safety contracts with synthetic fixtures and no PostgreSQL connections."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np

from experiments.association import database as db, runner
from experiments.association.protocol import FILTERS, METHODS, MODES, PROTOCOL, STAGES, stage_config
from experiments.milestone2.artifacts import verify_checksum_manifest, write_json_exclusive
from experiments.milestone2.database import TimedResult


class Cursor:
    def __init__(self, rows=()):
        self.rows, self.executions = list(rows), []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, statement, parameters=(), *, prepare=False):
        self.executions.append((statement, parameters, prepare))

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows=()):
        self.handle, self.closed = Cursor(rows), False

    def cursor(self):
        return self.handle

    def close(self):
        self.closed = True


def prepared_connections(mode="legacy"):
    return {
        method: Connection([
            (f"stmt_{i}", db.search_sql(method, mode, threshold).replace("%s", "$1"),
             "{vector}", 1022, 0)
            for i, threshold in enumerate(FILTERS)
        ])
        for method in METHODS
    }


def truth():
    return {"canonical_ids": list(range(10)), "strictly_closer_ids": list(range(9)),
            "boundary_tie_ids": [9, 10], "record_sha256": "a" * 64}


class ResourceGateTests(unittest.TestCase):
    def test_exact_minimum_resource_values_are_allowed(self):
        runner.resource_gate(PROTOCOL, {
            "memory_available_bytes": PROTOCOL["resource_min_available_bytes"],
            "disk_free_bytes": PROTOCOL["resource_min_disk_bytes"],
        })

    def test_insufficient_memory_and_disk_each_fail_closed(self):
        for host_key, config_key, message in (
            ("memory_available_bytes", "resource_min_available_bytes", "memory"),
            ("disk_free_bytes", "resource_min_disk_bytes", "disk"),
        ):
            host = {"memory_available_bytes": 2**40, "disk_free_bytes": 2**40}
            host[host_key] = PROTOCOL[config_key] - 1
            with self.subTest(field=host_key), self.assertRaisesRegex(RuntimeError, message):
                runner.resource_gate(PROTOCOL, host)

    def test_missing_resource_measurement_is_not_treated_as_sufficient(self):
        with self.assertRaises(KeyError):
            runner.resource_gate(PROTOCOL, {"disk_free_bytes": 2**40})


class PredecessorTests(unittest.TestCase):
    def test_first_stage_has_no_predecessor_or_verification_call(self):
        with patch("experiments.association.verify.verify_run") as verify:
            self.assertIsNone(runner.check_predecessor(stage_config(*STAGES[0]), None, {}))
            verify.assert_not_called()
            with self.assertRaisesRegex(ValueError, "first stage"):
                runner.check_predecessor(stage_config(*STAGES[0]), Path("unexpected"), {})
            verify.assert_not_called()

    def test_every_later_stage_requires_predecessor(self):
        for stage in STAGES[1:]:
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "requires"):
                runner.check_predecessor(stage_config(*stage), None, {})

    def check(self, position=1, *, old_stage=None, source=None, proof=None):
        previous = Path("synthetic-predecessor")
        old_stage = STAGES[position - 1] if old_stage is None else old_stage
        source = {"experiments/association/runner.py": "bytes-v1"} if source is None else source
        proof = {"passed": True, "independent_check": "synthetic"} if proof is None else proof
        documents = {
            previous / "config.json": stage_config(*old_stage),
            previous / "manifest.json": {"source_file_sha256": source},
        }
        with patch.object(runner, "read_json", side_effect=lambda path: documents[Path(path)]), \
             patch("experiments.association.verify.verify_run", return_value=proof) as verify:
            value = runner.check_predecessor(stage_config(*STAGES[position]), previous,
                                             {"experiments/association/runner.py": "bytes-v1"})
        verify.assert_called_once_with(previous)
        return value

    def test_all_three_transitions_require_actual_previous_frozen_stage(self):
        for position in range(1, len(STAGES)):
            with self.subTest(position=position):
                result = self.check(position)
                self.assertEqual(result["run_directory"], str(Path("synthetic-predecessor").resolve()))
                self.assertTrue(result["verification"]["passed"])

    def test_skipped_or_reordered_stage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "previous frozen stage"):
            self.check(position=2, old_stage=STAGES[0])

    def test_source_bytes_must_match_even_if_stage_order_is_right(self):
        for changed in ({"experiments/association/runner.py": "bytes-v2"}, {}):
            with self.subTest(source=changed), self.assertRaisesRegex(ValueError, "implementation changed"):
                self.check(source=changed)

    def test_independent_verification_failure_cannot_be_bypassed(self):
        with patch("experiments.association.verify.verify_run", side_effect=AssertionError("bad checksum")), \
             patch.object(runner, "read_json") as read:
            with self.assertRaisesRegex(AssertionError, "bad checksum"):
                runner.check_predecessor(stage_config(*STAGES[1]), Path("bad"), {})
            read.assert_not_called()


class PreparedEvidenceTests(unittest.TestCase):
    def test_empty_or_incomplete_method_matrix_is_rejected(self):
        incomplete = prepared_connections()
        incomplete.pop("hnsw_iterative")
        for connections in ({}, incomplete):
            with self.subTest(methods=tuple(connections)), self.assertRaises(AssertionError):
                runner.prepared_evidence(connections, "legacy")

    def test_both_modes_have_five_single_vector_statements_per_method(self):
        for mode in MODES:
            connections = prepared_connections(mode)
            observed = runner.prepared_evidence(connections, mode)
            self.assertEqual(set(observed), set(METHODS))
            for method, rows in observed.items():
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(row["generic_plans"] == 1022 and row["custom_plans"] == 0 for row in rows))
                self.assertTrue(all(row["parameter_types"] == "{vector}" for row in rows))
                self.assertEqual({r["statement"] for r in rows}, {
                    db.search_sql(method, mode, t).replace("%s", "$1") for t in FILTERS})
                self.assertFalse(connections[method].handle.executions[0][2])

    def test_wrong_generic_custom_or_vector_parameter_counts_rejected(self):
        for index, value in ((2, "{vector,vector}"), (3, 1021), (3, 1023), (4, 1)):
            connections = prepared_connections()
            changed = list(connections["exact"].handle.rows[0])
            changed[index] = value
            connections["exact"].handle.rows[0] = tuple(changed)
            with self.subTest(index=index, value=value), self.assertRaisesRegex(AssertionError, "prepared"):
                runner.prepared_evidence(connections, "legacy")

    def test_other_mode_or_method_sql_is_rejected(self):
        for statement in (db.search_sql("exact", "radial", 50), db.search_sql("hnsw_standard", "legacy", 50)):
            connections = prepared_connections()
            row = list(connections["exact"].handle.rows[0])
            row[1] = statement.replace("%s", "$1")
            connections["exact"].handle.rows[0] = tuple(row)
            with self.subTest(statement=statement), self.assertRaisesRegex(AssertionError, "prepared"):
                runner.prepared_evidence(connections, "legacy")

    def test_missing_duplicate_or_extra_filter_statement_rejected(self):
        for mutation in ("missing", "duplicate", "extra"):
            connections = prepared_connections()
            rows = connections["exact"].handle.rows
            if mutation == "missing":
                rows.pop()
            elif mutation == "duplicate":
                rows[1] = rows[0]
            else:
                rows.append(rows[0])
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                runner.prepared_evidence(connections, "legacy")

    def test_unrelated_setting_statements_do_not_inflate_query_budget(self):
        connections = prepared_connections()
        for connection in connections.values():
            connection.handle.rows.append(("setting", "SELECT current_setting($1)", "{text}", 1, 0))
        self.assertEqual(len(runner.prepared_evidence(connections, "legacy")["exact"]), 5)


class ObservationTests(unittest.TestCase):
    def observation(self, *, mode="radial", method="hnsw_standard", phase="measured",
                    rows=None, selected=None, reference=None, error=None):
        vector = np.zeros(128, dtype=np.float32)
        base = {"metadata_mode": mode, "method": method, "filter_threshold": 5, "phase": phase,
                "scale_rows": 100000, "build_number": 1, "query_id": 23, "repetition": 1,
                "run_id": "synthetic-run", "config_sha256": "c" * 64, "backend_pid": 42,
                "plan_audit_id": "plan", "block_index": 1}
        timed = TimedResult([(i, float(i)) for i in range(10)] if rows is None else rows,
                            123456, None if error is None else error, None if error is None else "synthetic failure")
        if reference is None and phase != "disjoint_warmup":
            reference = truth()
        with patch.object(runner, "timed_execute_fetch", return_value=timed) as execute, \
             patch.object(runner.time, "perf_counter_ns", return_value=9000000):
            result = runner.observation(object(), vector, base, 17,
                                        {i: 0 for i in range(11)} if selected is None else selected, reference)
        return result, execute.call_args, vector

    def test_mode_specific_sql_has_one_bound_vector_and_full_provenance(self):
        for mode in MODES:
            result, call, vector = self.observation(mode=mode)
            sql = db.search_sql("hnsw_standard", mode, 5)
            self.assertEqual(call.args[1], sql)
            self.assertEqual(len(call.args[2]), 1)
            self.assertIs(call.args[2][0], vector)
            self.assertEqual(result["metadata_mode"], mode)
            self.assertEqual(result["sql_sha256"], hashlib.sha256(sql.encode()).hexdigest())
            self.assertEqual(result["ground_truth_record_sha256"], truth()["record_sha256"])
            self.assertEqual(result["sequence_index"], 17)
            self.assertEqual(result["duration_ns"], 123456)
            self.assertEqual(result["start_monotonic_ns"], 9000000)
            self.assertTrue(result["prepared"])
            runner.assert_valid_row(result)

    def test_canonical_and_tie_credit_are_distinguished(self):
        rows = [(i, float(i)) for i in range(9)] + [(10, 9.0)]
        result, _, _ = self.observation(rows=rows)
        self.assertEqual(result["canonical_recall_at_10"], .9)
        self.assertEqual(result["tie_aware_recall_at_10"], 1)
        runner.assert_valid_row(result)

    def test_warmup_never_claims_ground_truth_or_recall(self):
        result, _, _ = self.observation(phase="disjoint_warmup")
        self.assertIsNone(result["canonical_recall_at_10"])
        self.assertIsNone(result["tie_aware_recall_at_10"])
        self.assertIsNone(result["ground_truth_record_sha256"])
        runner.assert_valid_row(result)

    def test_missing_ann_results_reduce_recall_without_invalidating_run(self):
        for rows, recall in (([], 0), ([(i, float(i)) for i in range(3)], .3)):
            result, _, _ = self.observation(rows=rows)
            self.assertEqual(result["canonical_recall_at_10"], recall)
            self.assertEqual(result["shortfall"], 10 - len(rows))
            self.assertFalse(result["returned_k"])
            runner.assert_valid_row(result)

    def test_incomplete_or_inexact_exact_search_is_rejected(self):
        for rows in ([], [(i, float(i)) for i in range(9)] + [(10, 9.0)]):
            result, _, _ = self.observation(rows=rows, method="exact")
            with self.assertRaises(AssertionError):
                runner.assert_valid_row(result)

    def test_filter_validation_uses_selected_metadata_not_global_proportion(self):
        labels = {i: 0 for i in range(11)}
        labels[3] = 5
        result, _, _ = self.observation(selected=labels)
        self.assertFalse(result["filter_valid"])
        with self.assertRaisesRegex(AssertionError, "invalid results"):
            runner.assert_valid_row(result)

    def test_query_error_is_preserved_not_scored_as_valid_empty_result(self):
        for error in ("QueryCanceled", "OperationalError"):
            result, _, _ = self.observation(rows=[], error=error)
            self.assertEqual(result["error_type"], error)
            self.assertEqual(result["error_message"], "synthetic failure")
            self.assertEqual(result["timeout"], error == "QueryCanceled")
            self.assertIsNone(result["canonical_recall_at_10"])
            self.assertIsNone(result["tie_aware_recall_at_10"])
            self.assertEqual(result["ground_truth_record_sha256"], truth()["record_sha256"])
            with self.assertRaisesRegex(AssertionError, "query failed"):
                runner.assert_valid_row(result)


@contextmanager
def mocked_stage(root: Path):
    """Exercise control flow with intentionally tiny mock data, never a benchmark."""
    source = {"dataset": {"expected_sha256": "d" * 64, "expected_bytes": 123},
              "scale_assignment": {"expected_ordered_ids_sha256": "o", "expected_cache_sha256": "c"}}
    documents = {root / "config/metadata-association-v1.json": copy.deepcopy(PROTOCOL),
                 root / PROTOCOL["source_protocol"]: source, runner.SOURCE_MANIFEST_PATH: {}}
    ids = np.arange(100, dtype=np.int32)
    vectors = np.zeros((100, 128), dtype=np.float32)
    queries = {"measured_query_ids": list(range(200)), "warmup_query_ids": list(range(200, 220))}
    qvectors = {q: vectors[0] for q in range(220)}
    connections = []

    def connection(**kwargs):
        value = Connection()
        connections.append(value)
        return value

    with ExitStack() as stack:
        def mock(target, name, **kwargs):
            return stack.enter_context(patch.object(target, name, **kwargs))

        mocks = {}
        simple = {
            "ROOT": root, "read_json": None, "git_state": {"dirty": False, "status_porcelain": [], "commit": "a" * 40},
            "source_identity": {"experiments/association/runner.py": "source-bytes"},
            "make_run_id": "synthetic-run", "energy_mode": {"ac_power_detected": True},
            "host_environment": {"memory_available_bytes": 2**40, "disk_free_bytes": 2**40},
            "validate_source_manifest_identity": {"passed": True},
            "validate_hdf5": {"byte_size": 123, "sha256": "d" * 64},
            "ensure_scale_order": (ids, {}), "build_scale_manifest": {"selected_base_ids": ids, "filter_buckets": ids},
            "serializable_scale_manifest": {}, "load_scale_vectors": vectors,
            "build_metadata": (ids.copy(), {}), "select_query_ids": queries,
            "load_query_vectors": qvectors, "neighborhoods": [], "association_diagnostics": {"gate_passed": True},
            "acquire_campaign_lock": None, "guard_other_clients": [],
            "verify_versions": {"postgresql_version": "17.11", "pgvector_version": "0.8.6"},
            "validate_server_settings": {}, "postgres_settings": [],
            "configure_session": (42, {}), "validate_ground_truth_numpy": {"passed": True},
            "ground_truth_index": {(q, t): truth() for q in range(200) for t in FILTERS},
            "evict_shared_buffers": {},
        }
        for name, value in simple.items():
            if name == "ROOT":
                mock(runner, name, new=value)
            elif name == "read_json":
                mocks[name] = mock(runner, name, side_effect=lambda path: copy.deepcopy(documents[Path(path)]))
            else:
                mocks[name] = mock(runner, name, return_value=value)
        mocks["connect"] = mock(runner, "connect", side_effect=connection)
        file = mock(runner.h5py, "File")
        file.return_value.__enter__.return_value = {"train": vectors}
        for name, value in {"load_scale": {}, "evidence": {}, "identity": {"same_graph": True},
                            "generate_truth": ([{"synthetic": True}] * 1000, 1)}.items():
            mocks[name] = mock(db, name, return_value=value)
        mocks["audit_plan"] = mock(db, "audit_plan", side_effect=lambda connection, **kw: (
            f"{kw['method']}_{kw['mode']}_{kw['threshold']}", [{"synthetic": True}], {"passed": True}))
        yield mocks, connections


class FailureFinalizationTests(unittest.TestCase):
    def assert_invalid(self, root, phase):
        run_dir = root / "raw_results/association/synthetic-run"
        self.assertTrue((run_dir / "INVALID.json").is_file())
        self.assertFalse((run_dir / "ACTIVE").exists())
        self.assertFalse((run_dir / "COMPLETE.json").exists())
        verify_checksum_manifest(run_dir)
        failure = json.loads((run_dir / "failure.json").read_text())
        self.assertEqual(failure["phase"], phase)
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            write_json_exclusive(run_dir / "cannot_append.json", {"no": "overwrite"})
        return run_dir, failure

    def test_dirty_tree_rejected_before_artifact_or_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mocked_stage(root) as (mocks, _):
                mocks["git_state"].return_value = {"dirty": True, "status_porcelain": [" M source.py"]}
                with self.assertRaisesRegex(RuntimeError, "clean committed"):
                    runner.run_stage(*STAGES[0])
                mocks["connect"].assert_not_called()
            self.assertFalse((root / "raw_results").exists())

    def test_wrong_frozen_profile_rejected_before_artifact_or_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mocked_stage(root) as (mocks, _):
                mocks["read_json"].side_effect = lambda path: {**PROTOCOL, "repetitions": 1}
                with self.assertRaisesRegex(ValueError, "protocol differs"):
                    runner.run_stage(*STAGES[0])
                mocks["connect"].assert_not_called()
            self.assertFalse((root / "raw_results").exists())

    def test_power_or_resource_failure_finalizes_invalid_without_database_access(self):
        for failure_kind in ("power", "memory", "disk"):
            with self.subTest(failure_kind=failure_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with mocked_stage(root) as (mocks, _):
                    if failure_kind == "power":
                        mocks["energy_mode"].return_value = {"ac_power_detected": False}
                    else:
                        field = "memory_available_bytes" if failure_kind == "memory" else "disk_free_bytes"
                        mocks["host_environment"].return_value[field] = 0
                    with self.assertRaises(RuntimeError):
                        runner.run_stage(*STAGES[0])
                    mocks["connect"].assert_not_called()
                self.assert_invalid(root, "initialization")

    def test_bad_dataset_checksum_and_byte_size_each_finalize_invalid(self):
        for failure_kind in ("checksum", "size"):
            with self.subTest(failure_kind=failure_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with mocked_stage(root) as (mocks, _):
                    if failure_kind == "checksum":
                        mocks["validate_hdf5"].side_effect = AssertionError("bad checksum")
                    else:
                        mocks["validate_hdf5"].return_value["byte_size"] = 999
                    with self.assertRaises(AssertionError):
                        runner.run_stage(*STAGES[0])
                    mocks["connect"].assert_not_called()
                self.assert_invalid(root, "source_validation")

    def test_failed_association_manipulation_is_preserved_and_stops_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mocked_stage(root) as (mocks, _):
                mocks["association_diagnostics"].return_value = {"gate_passed": False, "synthetic": True}
                with self.assertRaisesRegex(AssertionError, "do not retune"):
                    runner.run_stage(*STAGES[0])
                mocks["connect"].assert_not_called()
                mocks["load_scale"].assert_not_called()
            run_dir, _ = self.assert_invalid(root, "association_qualification")
            self.assertFalse(json.loads((run_dir / "association_diagnostics.json").read_text())["gate_passed"])

    def test_database_load_failure_closes_control_connection_and_preserves_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mocked_stage(root) as (mocks, connections):
                mocks["load_scale"].side_effect = RuntimeError("synthetic load failure")
                with self.assertRaisesRegex(RuntimeError, "load failure"):
                    runner.run_stage(*STAGES[0])
            self.assertEqual(len(connections), 1)
            self.assertTrue(connections[0].closed)
            self.assert_invalid(root, "database_load")

    def test_failed_first_query_is_saved_in_partial_chunk_then_finalized_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mocked_stage(root) as (_, connections), \
                 patch.object(runner, "timed_execute_fetch", return_value=TimedResult([], 777, "QueryCanceled", "synthetic timeout")):
                with self.assertRaisesRegex(AssertionError, "query failed"):
                    runner.run_stage(*STAGES[0])
            self.assertEqual(len(connections), 4)
            self.assertTrue(all(c.closed for c in connections))
            run_dir, failure = self.assert_invalid(root, "legacy_measurement")
            partials = list(run_dir.glob("*.partial.jsonl"))
            self.assertEqual(len(partials), 1)
            rows = [json.loads(line) for line in partials[0].read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["sequence_index"], 1)
            self.assertEqual(rows[0]["error_type"], "QueryCanceled")
            self.assertTrue(rows[0]["timeout"])
            self.assertIsNone(rows[0]["canonical_recall_at_10"])
            self.assertEqual(failure["last_assigned_sequence_index"], 1)
            self.assertEqual(failure["durable_completed_chunks"], [])
            self.assertFalse((run_dir / partials[0].name.replace(".partial", "")).exists())


if __name__ == "__main__":
    unittest.main()
