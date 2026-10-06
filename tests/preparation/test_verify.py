"""Failure-focused tests for the independently implemented evidence checks."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.preparation import verify

from experiments.milestone2.database import search_sql
from experiments.preparation.verify import (
    FILTERS, METHODS, RELATIONS, validate_identity, validate_results,
    verify_chunks, verify_database, verify_manifest, verify_prepared, verify_row_provenance,
    verify_schedule_rows, verify_source_commit,
)


def result(ids=None, *, method="hnsw_standard"):
    ids = [1, 3] if ids is None else ids
    return {
        "result_ids": ids, "distances": [float(value) for value in ids],
        "filter_threshold": 50, "method": method, "returned_count": len(ids),
        "returned_k": len(ids) == 10, "shortfall": 10 - len(ids),
        "ids_unique": True, "scale_valid": True, "filter_valid": True,
        "distance_order_valid": True, "canonical_recall_at_10": 0.2,
        "tie_aware_recall_at_10": 0.2, "ground_truth_record_sha256": "truth",
    }


def truth():
    return {"canonical_ids": list(range(1, 11)), "strictly_closer_ids": [1, 2],
            "boundary_tie_ids": list(range(3, 13)), "record_sha256": "truth"}


class ResultValidationTests(unittest.TestCase):
    def test_missing_results_reduce_fixed_denominator_recall(self):
        validate_results(result(), {value: 0 for value in range(1, 20)}, truth())

    def test_empty_ann_results_are_valid_zero_recall(self):
        row = result([])
        row.update(canonical_recall_at_10=0, tie_aware_recall_at_10=0)
        validate_results(row, {}, truth())

    def test_boundary_tie_credit_not_canonical_credit(self):
        row = result([1, 11, 12])
        row.update(canonical_recall_at_10=0.1, tie_aware_recall_at_10=0.3)
        validate_results(row, {value: 0 for value in range(1, 20)}, truth())

    def test_wrong_metrics_completeness_duplicate_filter_order_rejected(self):
        for field, value in (("canonical_recall_at_10", 1.0), ("tie_aware_recall_at_10", float("nan")),
                             ("returned_k", True), ("shortfall", 0), ("ids_unique", 1),
                             ("result_ids", [1, 1]), ("result_ids", [1, 99]),
                             ("distances", [3.0, 1.0]), ("distances", [1.0, float("inf")])):
            with self.subTest(field=field, value=value):
                row = result()
                row[field] = value
                with self.assertRaises(AssertionError):
                    validate_results(row, {1: 0, 3: 0}, truth())

    def test_exact_incomplete_rejected(self):
        with self.assertRaisesRegex(AssertionError, "exact result"):
            validate_results(result(method="exact"), {1: 0, 3: 0}, truth())

    def test_disjoint_warmup_cannot_claim_truth(self):
        row = result()
        with self.assertRaises(AssertionError):
            validate_results(row, {1: 0, 3: 0}, None)
        row.update(canonical_recall_at_10=None, tie_aware_recall_at_10=None, ground_truth_record_sha256=None)
        validate_results(row, {1: 0, 3: 0}, None)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "data.json").write_text("{}\n")
        self.digest = hashlib.sha256((self.root / "data.json").read_bytes()).hexdigest()
        (self.root / "checksums.sha256").write_text(f"{self.digest}  data.json\n")
        (self.root / "COMPLETE.json").write_text("{}")

    def test_full_coverage_passes(self):
        self.assertEqual(verify_manifest(self.root), {"data.json": self.digest})

    def test_bytes_tamper_rejected(self):
        (self.root / "data.json").write_text("{ }\n")
        with self.assertRaisesRegex(AssertionError, "checksum mismatch"):
            verify_manifest(self.root)

    def test_unmanifested_file_rejected(self):
        (self.root / "extra.json").write_text("{}")
        with self.assertRaisesRegex(AssertionError, "coverage"):
            verify_manifest(self.root)

    def test_duplicate_and_unsafe_manifest_paths_rejected(self):
        for lines in (f"{self.digest}  data.json\n" * 2, f"{self.digest}  ../escape\n"):
            (self.root / "checksums.sha256").write_text(lines)
            with self.assertRaises(AssertionError):
                verify_manifest(self.root)

    def test_active_invalid_and_symlink_rejected(self):
        for marker in ("ACTIVE", "INVALID.json"):
            path = self.root / marker
            path.write_text("")
            with self.assertRaises(AssertionError):
                verify_manifest(self.root)
            path.unlink()
        (self.root / "link").symlink_to(self.root / "data.json")
        with self.assertRaisesRegex(AssertionError, "symlink"):
            verify_manifest(self.root)


def scheduled_fixture():
    block = {"block_index": 1, "method": "hnsw_standard", "filter_threshold": 1,
             "exposure_query_order": [102, 101], "query_order_by_repetition": [[101, 102]] * 5}
    schedule = {"builds": [{"build_number": 1, "arms": ["A", "B"], "blocks": [block]}]}
    rows = []
    for arm in ("A", "B"):
        phases = [("disjoint_warmup", 0, [201, 202])]
        if arm == "B":
            phases.append(("measured_exposure", 0, [102, 101]))
        phases.extend(("measured", repetition, [101, 102]) for repetition in range(1, 6))
        for phase, repetition, ids in phases:
            for query in ids:
                rows.append({"build_number": 1, "arm": arm, "block_index": 1, "method": "hnsw_standard",
                             "filter_threshold": 1, "phase": phase, "repetition": repetition,
                             "query_id": query, "sequence_index": len(rows) + 1})
    return schedule, [r for r in rows if r["phase"] == "measured"], [r for r in rows if r["phase"] != "measured"]


class ScheduleAndPreparedTests(unittest.TestCase):
    def test_interleaved_preparation_schedule_passes(self):
        schedule, measured, prepared = scheduled_fixture()
        verify_schedule_rows(measured, prepared, schedule, [101, 102], [201, 202])

    def test_missing_duplicate_unknown_arm_and_wrong_order_rejected(self):
        for corruption in ("missing", "duplicate", "arm", "order", "phase"):
            schedule, measured, prepared = scheduled_fixture()
            if corruption == "missing":
                measured.pop()
            elif corruption == "duplicate":
                measured[-1] = measured[0]
            elif corruption == "arm":
                measured[0]["arm"] = "C"
            elif corruption == "order":
                measured[0]["query_id"] = 102
            else:
                prepared[0]["phase"] = "measured"
            with self.subTest(corruption=corruption), self.assertRaises(AssertionError):
                verify_schedule_rows(measured, prepared, schedule, [101, 102], [201, 202])

    def test_wrong_exposure_permutation_rejected(self):
        schedule, measured, prepared = scheduled_fixture()
        schedule["builds"][0]["blocks"][0]["exposure_query_order"] = [101, 101]
        with self.assertRaisesRegex(AssertionError, "exposure permutation"):
            verify_schedule_rows(measured, prepared, schedule, [101, 102], [201, 202])

    def test_exact_prepared_counts_enforced(self):
        for arm, count in (("A", 1022), ("B", 1222)):
            prepared = {method: [
                {"name": str(t), "statement": search_sql(method, t, 10).replace("%s", "$1"),
                 "parameter_types": "{vector}", "generic_plans": count, "custom_plans": 0}
                for t in FILTERS] for method in METHODS}
            verify_prepared(prepared, arm)
            for field, wrong in (("generic_plans", count - 1), ("custom_plans", 1), ("parameter_types", "{vector,vector}")):
                changed = copy.deepcopy(prepared)
                changed["exact"][0][field] = wrong
                with self.subTest(arm=arm, field=field), self.assertRaises(AssertionError):
                    verify_prepared(changed, arm)
            with self.assertRaises(AssertionError):
                verify_prepared(prepared, "C")

    def test_distinct_physical_objects_required(self):
        identity = {"server_version_num": "170011", "system_identifier": "cluster", "database": "db",
                    "relations": [{"relation": name, "kind": kind, "oid": n, "filenode": n + 10}
                                  for n, (name, kind) in enumerate(RELATIONS.items(), 1)]}
        validate_identity(identity)
        identity["relations"][1]["oid"] = identity["relations"][0]["oid"]
        with self.assertRaisesRegex(AssertionError, "physical oid"):
            validate_identity(identity)

    def test_error_timeout_invalid_clock_and_wrong_sql_rejected(self):
        row = {"run_id": "run", "config_sha256": "digest", "scale_rows": 100000, "k": 10, "prepared": True,
               "backend_pid": 123, "plan_audit_id": "plan", "method": "exact", "filter_threshold": 1,
               "sql_sha256": hashlib.sha256(search_sql("exact", 1, 10).encode()).hexdigest(),
               "error_type": None, "error_message": None, "timeout": False, "duration_ns": 10,
               "start_monotonic_ns": 100}
        verify_row_provenance(row, "run", "digest", 123, "plan")
        for name, value in (("error_type", "Timeout"), ("timeout", True), ("duration_ns", -1),
                            ("duration_ns", True), ("start_monotonic_ns", 0), ("sql_sha256", "wrong")):
            changed = {**row, name: value}
            with self.subTest(field=name), self.assertRaises(AssertionError):
                verify_row_provenance(changed, "run", "digest", 123, "plan")

    def test_consolidation_equals_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"phase": "measured", "sequence_index": 1}, {"phase": "measured", "sequence_index": 2}]
            path = root / "chunk_test.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            journal = {"chunks": [{"file": path.name, "phase": "measured", "row_count": 2,
                        "first_sequence_index": 1, "last_sequence_index": 2,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}
            verify_chunks(root, journal, rows, [])
            with self.assertRaisesRegex(AssertionError, "consolidations"):
                verify_chunks(root, journal, list(reversed(rows)), [])
            (root / "chunk_extra.partial.jsonl").write_text("{}\n")
            with self.assertRaisesRegex(AssertionError, "coverage"):
                verify_chunks(root, journal, rows, [])


class ProducerContractTests(unittest.TestCase):
    def test_legacy_database_evidence_shape_remains_compatible(self):
        # The new runner intentionally reuses this exact producer contract.
        path = verify.ROOT / "raw_results/milestone_2/20260929T172504Z_fa89b474a1c4/database_evidence.json"
        evidence = json.loads(path.read_text())
        digest = evidence["source_vector_stream_sha256"]
        verify_database(evidence, {}, digest)
        for name, value in (("nonfinite_vector_counts", {"exact": 1, "hnsw": 0}),
                            ("exact_count", 99999), ("ordered_vector_stream_sha256", "wrong")):
            with self.subTest(field=name), self.assertRaises(AssertionError):
                verify_database({**evidence, name: value}, {}, digest)

    def test_git_source_contract_uses_recorded_commit_not_current_checkout(self):
        config = {"source_protocol": "config/milestone2/protocol.json"}
        blobs = {config["source_protocol"]: b'{"dataset":"source"}',
                 "config/preparation-policy-v1.json": json.dumps(config).encode(),
                 "experiments/preparation/runner.py": b"example source"}
        commit = "a" * 40
        manifest = {"git_at_start": {"commit": commit, "dirty": False, "status_porcelain": []},
                    "source_protocol": {"dataset": "source"},
                    "source_file_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in blobs.items()}}

        def git(command, **kwargs):
            if command[1] == "show":
                self.assertTrue(command[2].startswith(commit + ":"))
                return type("Result", (), {"stdout": blobs[command[2].split(":", 1)[1]]})()
            self.assertEqual(command[1:5], ["ls-tree", "-r", "--name-only", commit])
            return type("Result", (), {"stdout": "\n".join(blobs)})()

        with patch.object(verify.subprocess, "run", side_effect=git):
            self.assertEqual(verify_source_commit(manifest, config), {"dataset": "source"})
            changed = copy.deepcopy(manifest)
            changed["source_file_sha256"].pop("experiments/preparation/runner.py")
            with self.assertRaisesRegex(AssertionError, "inventory"):
                verify_source_commit(changed, config)
            changed = copy.deepcopy(manifest)
            changed["git_at_start"]["status_porcelain"] = [" M file"]
            with self.assertRaisesRegex(AssertionError, "clean Git"):
                verify_source_commit(changed, config)


if __name__ == "__main__":
    unittest.main()
