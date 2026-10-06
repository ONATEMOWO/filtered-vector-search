"""Offline formula, provenance, schedule and exclusive-output analysis tests."""

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis import preparation_policy as analysis
from experiments.preparation.protocol import PROTOCOL, build_schedule


def row(query=0, repetition=1, duration=1_000_000):
    return {"query_id": query, "repetition": repetition, "duration_ns": duration,
            "method": "exact", "filter_threshold": 1,
            "result_ids": list(range(10)), "distances": list(range(10)),
            "canonical_recall_at_10": 1.0, "tie_aware_recall_at_10": 1.0,
            "returned_count": 10, "returned_k": True,
            "error_type": None, "error_message": None, "timeout": False}


def queries(patterns):
    return {q: {r: row(q, r, duration) for r, duration in enumerate(values, 1)}
            for q, values in enumerate(patterns)}


def seal(path):
    (path / "checksums.sha256").write_text("".join(
        f"{analysis.sha256(p)}  {p.name}\n" for p in sorted(path.iterdir())
        if p.name not in {"COMPLETE.json", "checksums.sha256"}), encoding="utf-8")


def fixture(path):
    path.mkdir()
    measured, warmup = list(range(200)), list(range(200, 220))
    schedule = build_schedule(PROTOCOL, measured)
    documents = {"config.json": PROTOCOL, "COMPLETE.json": {"valid": True},
                 "queries.json": {"measured_query_ids": measured, "warmup_query_ids": warmup},
                 "schedule.json": schedule}
    for name, value in documents.items():
        (path / name).write_text(json.dumps(value), encoding="utf-8")
    measured_rows, preparation_rows = [], []
    sequence = 0
    for build in schedule["builds"]:
        for arm in build["arms"]:
            for block in build["blocks"]:
                phases = [("disjoint_warmup", warmup, 0)]
                if arm == "B":
                    phases.append(("measured_exposure", block["exposure_query_order"], 0))
                phases.extend(("measured", ids, r) for r, ids in enumerate(block["query_order_by_repetition"], 1))
                for phase, ids, repetition in phases:
                    for query in ids:
                        sequence += 1
                        pattern = [10, 1, 1.1, 1.2, 1.3] if arm == "A" else [1.1, 1, 1.01, 1.02, 1.03]
                        duration = int(pattern[max(repetition - 1, 0)] * 1e6) + query
                        record = {**row(query, repetition, duration), "run_id": path.name,
                                  "build_number": build["build_number"], "arm": arm, "phase": phase,
                                  "method": block["method"], "filter_threshold": block["filter_threshold"],
                                  "sequence_index": sequence}
                        (measured_rows if phase == "measured" else preparation_rows).append(record)
    for name, rows in (("executions.jsonl", measured_rows), ("preparation.jsonl", preparation_rows)):
        (path / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    seal(path)
    return measured_rows, preparation_rows


class FormulaTests(unittest.TestCase):
    def test_percentile_linear_interpolation(self):
        self.assertEqual(analysis.percentile([1, 2, 3, 4, 5]), 4.8)
        self.assertEqual(analysis.percentile([7]), 7)
        with self.assertRaises(ValueError):
            analysis.percentile([])

    def test_primary_hierarchy_is_not_pooled_request_median(self):
        sample = queries([[1, 1, 100, 100, 100], [2, 2, 2, 2, 2]])
        result = analysis.summarize_condition(sample)
        self.assertEqual(result["all_five_median_query_median_ms"], 51 / 1e6)
        self.assertNotEqual(result["all_five_median_query_median_ms"], 2 / 1e6)
        self.assertEqual(result["pass_raw_request_p95_ms"][0], 1.95 / 1e6)
        self.assertEqual(result["all_five_p95_query_median_ms"], 95.1 / 1e6)

    def test_paired_ratio_is_not_ratio_of_condition_medians(self):
        sample = queries([[100, 1, 1, 1, 1], [20, 100, 100, 100, 100], [1, 10, 10, 10, 10]])
        result = analysis.summarize_condition(sample)
        self.assertEqual(result["median_paired_first_over_later"], .2)
        self.assertAlmostEqual(result["median_abs_log2_first_over_later"], abs(math.log2(.1)))
        self.assertEqual(result["later_pass_max_over_min"], 1)

    def test_first_faster_also_has_log_deviation(self):
        result = analysis.summarize_condition(queries([[1, 2, 2, 2, 2]]))
        self.assertEqual(result["median_abs_log2_first_over_later"], 1)
        self.assertTrue(result["engineering_20pct_flag"])

    def test_engineering_band_inclusive(self):
        self.assertFalse(analysis.summarize_condition(queries([[80, 100, 100, 100, 120]]))["engineering_20pct_flag"])
        self.assertTrue(analysis.summarize_condition(queries([[79, 100, 100, 100, 120]]))["engineering_20pct_flag"])

    def test_quality_counts_include_distances(self):
        sample = queries([[1] * 5])
        sample[0][5]["distances"][-1] += .1
        result = analysis.summarize_condition(sample)
        self.assertEqual(result["ordered_results_stable_query_count"], 1)
        self.assertEqual(result["quality_stable_query_count"], 0)

    def test_paired_arm_latency_and_quality(self):
        a = queries([[1] * 5, [10] * 5, [100] * 5])
        b = queries([[100] * 5, [1] * 5, [20] * 5])
        result = analysis.compare_arms(a, b)
        self.assertEqual(result["median_paired_B_over_A_query_median_latency"], .2)
        self.assertEqual(result["quality_identical_query_count"], 3)
        b[1][5]["distances"][-1] = 9.5
        self.assertEqual(analysis.compare_arms(a, b)["quality_changed_query_count"], 1)
        a[1][5]["distances"][-1] = 9.5
        result = analysis.compare_arms(a, b)
        self.assertEqual(result["quality_changed_query_count"], 0)
        self.assertEqual(result["quality_unstable_across_arms_or_repetitions_count"], 1)

    def test_directional_support_requires_both_metrics_both_builds(self):
        sample = [{"build_number": b, "A_abs_log2_first_later": 2, "B_abs_log2_first_later": 1,
                   "A_later_pass_max_over_min": 1.2, "B_later_pass_max_over_min": 1.1,
                   "quality_changed_query_count": 0,
                   "quality_unstable_across_arms_or_repetitions_count": 0} for b in (1, 2)]
        self.assertTrue(analysis.directional_support(sample)["supported_without_quality_change"])
        sample[1]["B_later_pass_max_over_min"] = 1.2
        self.assertFalse(analysis.directional_support(sample)["timing_directional_criterion_both_builds"])
        sample[1]["B_later_pass_max_over_min"] = 1.1
        sample[1]["quality_changed_query_count"] = 1
        result = analysis.directional_support(sample)
        self.assertTrue(result["timing_directional_criterion_both_builds"])
        self.assertFalse(result["supported_without_quality_change"])
        with self.assertRaises(ValueError):
            analysis.directional_support(sample[:1])
        sample[1]["quality_changed_query_count"] = 0
        sample[1]["quality_unstable_across_arms_or_repetitions_count"] = 1
        self.assertFalse(analysis.directional_support(sample)["supported_without_quality_change"])

    def test_bad_row_values(self):
        for change in ({"duration_ns": 0}, {"duration_ns": True}, {"duration_ns": float("nan")},
                       {"returned_k": False}, {"canonical_recall_at_10": float("inf")},
                       {"tie_aware_recall_at_10": .9}, {"distances": [float("nan")] * 10},
                       {"distances": list(reversed(range(10)))}, {"error_type": "timeout"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                analysis.validate_row({**row(), **change}, measured=True)

    def test_grid_rejects_duplicate_missing_and_unknown(self):
        sample = [row(0, r) for r in range(1, 6)]
        key = lambda r: (r["method"], r["filter_threshold"])
        self.assertEqual(len(analysis.group_measured(sample, key, {("exact", 1)}, [0])), 1)
        for bad in (sample[:-1], sample + [sample[0]], [{**sample[0], "query_id": 1}] + sample[1:]):
            with self.assertRaises(ValueError):
                analysis.group_measured(bad, key, {("exact", 1)}, [0])

    def test_query_selection_rejects_overlap(self):
        with self.assertRaises(ValueError):
            analysis.query_ids({"measured_query_ids": list(range(200)), "warmup_query_ids": list(range(20))})


class PilotArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.run_path = cls.root / "synthetic-pilot"
        cls.rows, cls.prep = fixture(cls.run_path)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_complete_pilot_analysis_and_inputs_unchanged(self):
        before = analysis.snapshot(self.run_path)
        report = analysis.analyze_pilot(self.run_path)
        self.assertEqual(report["counts"], {"measured": 60000, "preparation": 7200, "conditions": 60,
                         "query_ids_per_condition": 200, "distinct_graph_builds": 2})
        self.assertEqual(len(report["arm_comparisons"]), 30)
        self.assertTrue(all(c["supported_without_quality_change"] for c in report["directional_support"]))
        self.assertEqual(sum(c["query_count"] for c in report["preparation"]), 7200)
        self.assertEqual(before, analysis.snapshot(self.run_path))
        text = analysis.markdown(report)
        self.assertIn("not final research findings", text)
        self.assertIn("All five repetitions", text)

    def test_schedule_permutation_and_chronology_checked_independently(self):
        schedule = analysis.read_json(self.run_path / "schedule.json")
        malformed = copy.deepcopy(schedule)
        malformed["builds"][0]["blocks"][0]["query_order_by_repetition"][0].reverse()
        with self.assertRaisesRegex(ValueError, "permutations"):
            analysis.validate_pilot_schedule(self.rows, self.prep, malformed, list(range(200)), list(range(200, 220)))
        changed = list(self.rows)
        changed[0] = {**changed[0], "query_id": changed[1]["query_id"]}
        with self.assertRaisesRegex(ValueError, "chronology"):
            analysis.validate_pilot_schedule(changed, self.prep, schedule, list(range(200)), list(range(200, 220)))

    def test_generation_sealed_and_exclusive(self):
        output = self.root / "complete-output"
        # Real figures are separately exercised; mock only rendering in this test.
        with patch.object(analysis, "figures", return_value={"matplotlib": "test fixture"}):
            report = analysis.generate("pilot", [self.run_path], output)
        marker = analysis.read_json(output / "COMPLETE.json")
        self.assertEqual(marker["checksums_sha256"], analysis.sha256(output / "checksums.sha256"))
        self.assertEqual(report, analysis.read_json(output / "analysis.json"))
        with patch.object(analysis, "analyze_pilot") as inspect:
            with self.assertRaises(FileExistsError):
                analysis.generate("pilot", [self.run_path], output)
            inspect.assert_not_called()

    def test_three_static_figures_render_from_synthetic_pilot(self):
        report = analysis.analyze_pilot(self.run_path)
        output = self.root / "synthetic-figures"
        output.mkdir()
        dependencies = analysis.figures(report, output)
        self.assertIn("matplotlib", dependencies)
        self.assertEqual({p.name for p in output.iterdir()}, {
            "first_later_deviation.png", "later_pass_spread.png", "paired_latency_ratio.png"})
        for path in output.iterdir():
            self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(path.stat().st_size, 10000)

    def test_late_failure_preserves_partial_without_complete(self):
        output = self.root / "partial-output"
        real = analysis.verify_inputs
        calls = 0
        def fail_last(report):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("input changed during analysis")
            return real(report)
        with patch.object(analysis, "figures", return_value={}), patch.object(analysis, "verify_inputs", side_effect=fail_last):
            with self.assertRaisesRegex(ValueError, "changed"):
                analysis.generate("pilot", [self.run_path], output)
        self.assertTrue((output / "analysis.json").is_file())
        self.assertFalse((output / "COMPLETE.json").exists())
        self.assertFalse((output / "checksums.sha256").exists())

    def test_bad_output_and_checksum_coverage(self):
        with self.assertRaises(ValueError):
            analysis.generate("pilot", [self.run_path], self.root / "raw_results" / "not-allowed")
        with self.assertRaises(ValueError):
            analysis.generate("pilot", [self.run_path], self.run_path / "not-allowed")
        extra = self.run_path / "unmanifested.txt"
        extra.write_text("temporary negative-test fixture", encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "coverage"):
                analysis.snapshot(self.run_path)
        finally:
            extra.unlink()


if __name__ == "__main__":
    unittest.main()
