"""Synthetic, temporary-fixture tests; no PostgreSQL or research artifacts touched."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis import audit_repetition_sensitivity as audit


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def seal(run):
    lines = [f"{audit.sha256(p)}  {p.name}\n" for p in sorted(run.iterdir())
             if p.is_file() and p.name not in {"checksums.sha256", "COMPLETE.json"}]
    (run / "checksums.sha256").write_text("".join(lines), encoding="utf-8")


def fixture(root, round_number):
    run = root / f"synthetic-round-{round_number}"
    run.mkdir()
    stage_id = f"benchmark-100k-round-{round_number}"
    identity = {"run_id": run.name, "stage_id": stage_id, "experiment_round": round_number}
    write_json(run / "COMPLETE.json", {**identity, "valid": True,
               "qualification_only": False, "timed_executions": 15000})
    write_json(run / "run_manifest.json", {**identity, "git_at_start": {"commit": "a" * 40}})
    write_json(run / "queries.json", {"measured_query_ids": list(range(200))})
    write_json(run / "config.json", {"stage": {"stage_id": stage_id,
               "campaign_id": "standalone-100k-v1",
               "experiment_round": round_number, "scale_rows": 100000,
               "timed_query_count": 200, "repetitions": 5, "rounds": 1,
               "expected_timed_executions": 15000}})
    rows = [{"run_id": run.name, "stage_id": stage_id, "round": round_number,
             "build_id": f"{run.name}-round-{round_number}-build-1", "scale_rows": 100000,
             "k": 10, "method": method, "filter_threshold": threshold,
             "query_id": query, "repetition": repetition,
             "duration_ns": (10 if repetition == 1 else 1) * 1000000 + query,
             "error_type": None, "error_message": None, "timeout": False,
             "result_ids": [query], "returned_count": 1}
            for method in audit.METHODS for threshold in audit.FILTERS
            for query in range(200) for repetition in range(1, 6)]
    write_rows(run, rows)
    return run


def write_rows(run, rows):
    (run / "executions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    seal(run)


class FormulaTests(unittest.TestCase):
    def test_paired_ratios_not_ratio_of_medians(self):
        queries = {q: {r: {"duration_ns": first if r == 1 else later, "result_ids": [q]}
                       for r in range(1, 6)}
                   for q, (first, later) in enumerate([(100, 1), (20, 100), (1, 10)])}
        actual = audit.summarize_condition(queries)
        self.assertEqual(actual["median_paired_first_over_later_four"], .2)
        self.assertNotEqual(actual["median_paired_first_over_later_four"], 2)
        self.assertEqual(actual["fraction_queries_first_slower_than_later_four_median"], 1 / 3)
        self.assertEqual(actual["ordered_results_identical_queries"], 3)

    def test_fractional_later_median_and_ordered_results(self):
        queries = {1: {r: {"duration_ns": value, "result_ids": [1, 2] if r < 5 else [2, 1]}
                       for r, value in enumerate([99, 1, 2, 3, 4], 1)}}
        actual = audit.summarize_condition(queries)
        self.assertEqual(actual["all_five_declared"]["median_query_median_ms"], 3 / 1e6)
        self.assertEqual(actual["later_four_sensitivity_only"]["median_query_median_ms"], 2.5 / 1e6)
        self.assertEqual(actual["ordered_results_changed_queries"], 1)

    def test_percentile(self):
        self.assertAlmostEqual(audit.percentile([5, 1, 4, 2, 3], .95), 4.8)
        self.assertEqual(audit.percentile([7], .95), 7)
        with self.assertRaises(ValueError):
            audit.percentile([], .95)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runs = [fixture(self.root, r) for r in (1, 2)]

    def mutate_rows(self, operation):
        rows = [json.loads(line) for line in (self.runs[0] / "executions.jsonl").read_text().splitlines()]
        operation(rows)
        write_rows(self.runs[0], rows)

    def test_full_diagnostic_reproducible_and_inputs_unchanged(self):
        before = [audit.checked_snapshot(p) for p in self.runs]
        first = audit.generate(self.runs, self.root / "output-one")
        second = audit.generate(self.runs, self.root / "output-two")
        self.assertEqual(first, second)
        self.assertEqual(sum(len(r["conditions"]) for r in first["runs"]), 30)
        self.assertTrue(all(r["timed_executions"] == 15000 for r in first["runs"]))
        self.assertEqual(before, [audit.checked_snapshot(p) for p in self.runs])
        text = (self.root / "output-one" / "REPETITION_SENSITIVITY.md").read_text()
        self.assertIn("not a corrected benchmark", text)
        self.assertIn("Later-four sensitivity", text)
        output = self.root / "output-one"
        marker = audit.read_json(output / "COMPLETE.json")
        self.assertEqual(marker, {"schema_version": 1,
            "artifact_type": "offline_repetition_sensitivity_diagnostic", "success": True,
            "checksums_sha256": audit.sha256(output / "checksums.sha256")})
        checksums = dict(line.split("  ", 1)[::-1] for line in (output / "checksums.sha256").read_text().splitlines())
        self.assertEqual(set(checksums), {"diagnostic.json", "REPETITION_SENSITIVITY.md"})
        self.assertTrue(all(audit.sha256(output / name) == digest for name, digest in checksums.items()))

    def test_missing_grid_entry(self):
        self.mutate_rows(lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, "incomplete"):
            audit.diagnose(self.runs)

    def test_duplicate_entry(self):
        self.mutate_rows(lambda rows: rows.__setitem__(-1, dict(rows[0])))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit.diagnose(self.runs)

    def test_execution_error(self):
        self.mutate_rows(lambda rows: rows[0].update(error_type="QueryCanceled"))
        with self.assertRaisesRegex(ValueError, "errors"):
            audit.diagnose(self.runs)

    def test_missing_error_evidence(self):
        self.mutate_rows(lambda rows: rows[0].pop("error_type"))
        with self.assertRaisesRegex(ValueError, "errors"):
            audit.diagnose(self.runs)

    def test_invalid_completion(self):
        marker = audit.read_json(self.runs[0] / "COMPLETE.json")
        marker["valid"] = False
        write_json(self.runs[0] / "COMPLETE.json", marker)
        with self.assertRaisesRegex(ValueError, "marked valid"):
            audit.diagnose(self.runs)

    def test_query_selection_differs_between_rounds(self):
        write_json(self.runs[1] / "queries.json", {"measured_query_ids": list(reversed(range(200)))})
        seal(self.runs[1])
        with self.assertRaisesRegex(ValueError, "identical measured query selection"):
            audit.diagnose(self.runs)

    def test_bad_duration_types_and_values(self):
        for value in (True, 1.5, 0, -1, float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    audit.integer(value, "duration", 1)
        self.mutate_rows(lambda rows: rows[0].update(duration_ns=0))
        with self.assertRaisesRegex(ValueError, "duration"):
            audit.diagnose(self.runs)

    def test_checksum_tampering(self):
        (self.runs[0] / "queries.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksum"):
            audit.diagnose(self.runs)

    def test_requires_distinct_runs(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            audit.diagnose([self.runs[0], self.runs[0]])

    def test_build_identity(self):
        self.mutate_rows(lambda rows: rows[0].update(build_id="different-build"))
        with self.assertRaisesRegex(ValueError, "identity"):
            audit.diagnose(self.runs)

    def test_campaign_identity(self):
        config = audit.read_json(self.runs[0] / "config.json")
        config["stage"]["campaign_id"] = "another-campaign"
        write_json(self.runs[0] / "config.json", config)
        seal(self.runs[0])
        with self.assertRaisesRegex(ValueError, "profile"):
            audit.diagnose(self.runs)

    def test_refuses_existing_output_before_inspection(self):
        output = self.root / "existing"
        output.mkdir()
        (output / "preserved.txt").write_text("keep", encoding="utf-8")
        with patch.object(audit, "diagnose") as diagnose:
            with self.assertRaises(FileExistsError):
                audit.generate(self.runs, output)
            diagnose.assert_not_called()
        self.assertEqual((output / "preserved.txt").read_text(), "keep")

    def test_refuses_raw_results_output_before_inspection(self):
        with patch.object(audit, "diagnose") as diagnose:
            with self.assertRaisesRegex(ValueError, "outside raw"):
                audit.generate(self.runs, self.root / "raw_results" / "new")
            diagnose.assert_not_called()
        self.assertFalse((self.root / "raw_results").exists())

    def test_detects_hash_change_during_read(self):
        real = audit.checked_snapshot
        calls = 0
        def changing_snapshot(path):
            nonlocal calls
            calls += 1
            result = real(path)
            if calls == 3:
                result["COMPLETE.json"] = "0" * 64
            return result
        with patch.object(audit, "checked_snapshot", side_effect=changing_snapshot):
            with self.assertRaisesRegex(ValueError, "changed during"):
                audit.diagnose(self.runs)

    def test_partial_diagnostic_is_preserved_on_late_failure(self):
        output = self.root / "partial"
        with patch.object(audit, "markdown", side_effect=RuntimeError("test interruption")):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                audit.generate(self.runs, output)
        self.assertTrue((output / "diagnostic.json").is_file())
        self.assertFalse((output / "COMPLETE.json").exists())
        with self.assertRaises(FileExistsError):
            audit.generate(self.runs, output)

    def test_failed_final_input_check_leaves_no_completion_marker(self):
        output = self.root / "late-partial"
        real = audit.checked_snapshot
        calls = 0
        def changing_snapshot(path):
            nonlocal calls
            calls += 1
            result = real(path)
            if calls == 5:
                result["COMPLETE.json"] = "0" * 64
            return result
        with patch.object(audit, "checked_snapshot", side_effect=changing_snapshot):
            with self.assertRaisesRegex(ValueError, "before diagnostic completion"):
                audit.generate(self.runs, output)
        self.assertTrue((output / "diagnostic.json").is_file())
        self.assertTrue((output / "REPETITION_SENSITIVITY.md").is_file())
        self.assertFalse((output / "COMPLETE.json").exists())
        self.assertFalse((output / "checksums.sha256").exists())


if __name__ == "__main__":
    unittest.main()
