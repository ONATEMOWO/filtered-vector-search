"""Synthetic unit fixtures only; no database access or research measurements."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis import metadata_association as analysis
from experiments.association.protocol import FILTERS, METHODS, MODES, STAGES, stage_config


def row(query=0, repetition=1, duration=1_000_000, count=10, recall=1.0):
    return {"query_id": query, "repetition": repetition, "duration_ns": duration,
            "method": "exact", "filter_threshold": 1, "result_ids": list(range(count)),
            "distances": list(range(count)), "canonical_recall_at_10": recall,
            "tie_aware_recall_at_10": recall, "returned_count": count, "returned_k": count == 10,
            "error_type": None, "error_message": None, "timeout": False}


def cells(patterns):
    return {q: {r: row(q, r, value) for r, value in enumerate(pattern, 1)}
            for q, pattern in enumerate(patterns)}


def metadata(scale):
    return {"row_count": scale, "ordered_base_ids_int64_le_sha256": f"ids-{scale}",
            "radial_labels_int16_le_sha256": f"radial-{scale}",
            "anchor_float64_le_sha256": "fixed-anchor",
            "prefix_100k_ordered_base_ids_int64_le_sha256": "ids-100000",
            "prefix_100k_radial_labels_int16_le_sha256": "radial-100000"}


def contract_stages():
    return [{"scale_rows": scale, "build_number": build,
             "queries": {"measured": list(range(200)), "warmup": list(range(200, 220))},
             "dataset_sha256": "source", "source_file_sha256": {"runner": "source-code"},
             "metadata": metadata(scale)} for scale, build in STAGES]


def seal(path):
    (path / "checksums.sha256").write_text("".join(
        f"{analysis.sha256(p)}  {p.name}\n" for p in sorted(path.iterdir())
        if p.name not in {"checksums.sha256", "COMPLETE.json"}), encoding="utf-8")


def fixture(path):
    """Complete arithmetic grid with mocked independent verifier (not SIFT)."""
    path.mkdir()
    source = path.parent / "synthetic-source.bin"
    source.write_bytes(b"unit-test fixture, not SIFT or empirical benchmark data")
    measured, warmup = list(range(200)), list(range(200, 220))
    summary = {mode: {str(t): {str(size): {
        "query_count": 200, "local_fraction_quantiles_linear": {
            str(q): min(1.0, (t / 100) * (1 if mode == "legacy" else 2))
            for q in (0, .05, .25, .5, .75, .95, 1)}} for size in (40, 100, 1000)}
        for t in FILTERS} for mode in MODES}
    diagnostics = {"gate_passed": True, "groups": {"measured": {"summary": summary}},
                   "primary_by_filter": {str(t): {"legacy_D": .01, "radial_D": .1,
                                                  "permutation_D_p95_linear": .02, "passes": True}
                                         for t in FILTERS}}
    docs = {"config.json": stage_config(100000, 1), "COMPLETE.json": {"valid": True},
            "queries.json": {"measured_query_ids": measured, "warmup_query_ids": warmup},
            "dataset_manifest.json": {"path": str(source), "sha256": analysis.sha256(source)},
            "manifest.json": {"source_file_sha256": {"runner": "fake-source"},
                              "git_at_start": {"commit": "a" * 40}},
            "metadata_manifest.json": metadata(100000), "phase_metrics.json": {"test_load_ns": 1},
            "database_evidence.json": {"relation_sizes": []},
            "validation_report.json": {"elapsed_ns": 1}, "association_diagnostics.json": diagnostics}
    for name, value in docs.items():
        (path / name).write_text(json.dumps(value), encoding="utf-8")
    rows = []
    for mode in MODES:
        for method in METHODS:
            for threshold in FILTERS:
                for query in measured:
                    for repetition in range(1, 6):
                        quality_count = 10 if method == "exact" else (5 if mode == "legacy" else 7)
                        rows.append({**row(query, repetition, (1 if mode == "legacy" else 2)*1_000_000 + query,
                                           quality_count, quality_count / 10),
                                     "run_id": path.name, "phase": "measured", "scale_rows": 100000,
                                     "build_number": 1, "metadata_mode": mode, "method": method,
                                     "filter_threshold": threshold})
    neighbors = [{"query_id": q, "query_anchor_distance": q + 1.0,
                  "local_counts": {mode: {str(t): {str(size): min(size, q % 15)
                                                   for size in (40, 100, 1000)} for t in FILTERS}
                                   for mode in MODES}} for q in measured + warmup]
    files = {"executions.jsonl": rows, "neighbors.jsonl": neighbors}
    for mode in MODES:
        files[f"{mode}_ground_truth.jsonl"] = [
            {"query_id": q, "filter_threshold": t, "boundary_distance": q + t + 1.0}
            for q in measured for t in FILTERS]
    for name, records in files.items():
        (path / name).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    seal(path)
    return rows


class FormulaTests(unittest.TestCase):
    def test_average_ranks_handles_ties_and_original_order(self):
        self.assertEqual(analysis.average_ranks([20, 10, 20, 30]), [2.5, 1.0, 2.5, 4.0])
        self.assertEqual(analysis.average_ranks([]), [])
        for bad in ([float("nan")], [True], [float("inf")]):
            with self.assertRaises(ValueError):
                analysis.average_ranks(bad)

    def test_spearman_rank_ties(self):
        self.assertAlmostEqual(analysis.spearman([1, 2, 2, 4], [1, 2, 3, 4]), 3 / math.sqrt(10))
        self.assertEqual(analysis.spearman([1, 2, 3], [9, 4, 1]), -1)
        self.assertEqual(analysis.spearman([1, 2, 3], [1, 4, 9]), 1)
        with self.assertRaises(ValueError):
            analysis.spearman([1], [1, 2])

    def test_constant_and_singleton_rank_association_is_null(self):
        for a, b in (([1, 1], [1, 2]), ([1, 2], [4, 4]), ([1], [2]), ([], [])):
            self.assertIsNone(analysis.spearman(a, b))

    def test_paired_ratios_not_ratio_of_medians(self):
        left = cells([[1]*5, [10]*5, [100]*5])
        right = cells([[100]*5, [1]*5, [20]*5])
        result = analysis.compare_modes(left, right)
        self.assertEqual(result["median_paired_radial_over_legacy_query_median_latency"], .2)
        self.assertNotEqual(result["median_paired_radial_over_legacy_query_median_latency"], 2)
        self.assertEqual(result["paired_quality_deltas"]["returned_k"]["zero_query_count"], 3)

    def test_quality_deltas_average_all_five_repetitions(self):
        left, right = cells([[1]*5]), cells([[2]*5])
        right[0][5].update(canonical_recall_at_10=.5, tie_aware_recall_at_10=.6, returned_k=False, returned_count=5)
        result = analysis.compare_modes(left, right)["paired_quality_deltas"]
        self.assertAlmostEqual(result["canonical_recall_at_10"]["mean"], -.1)
        self.assertAlmostEqual(result["tie_aware_recall_at_10"]["mean"], -.08)
        self.assertAlmostEqual(result["returned_k"]["mean"], -.2)
        self.assertEqual(result["returned_count"]["mean"], -1)
        self.assertEqual(result["canonical_recall_at_10"]["negative_query_count"], 1)

    def test_paired_query_and_repetition_coverage_required(self):
        sample = cells([[1]*5])
        for other in ({}, {1: sample[0]}, {0: {1: sample[0][1]}}):
            with self.assertRaises(ValueError):
                analysis.compare_modes(sample, other)
        bad = cells([[0]*5])
        with self.assertRaises(ValueError):
            analysis.compare_modes(sample, bad)

    def test_density_bins_and_constant_quality_null(self):
        sample = cells([[1]*5, [2]*5, [3]*5, [4]*5])
        neighbors = {q: {"local_counts": {"legacy": {"5": {"40": n}}},
                         "query_anchor_distance": q + 1.0} for q, n in enumerate((0, 1, 9, 10))}
        truth = {(q, 5): {"boundary_distance": 100.0 + q} for q in sample}
        result = analysis.density_quality(sample, neighbors, truth, "legacy", 5)
        self.assertEqual([g["query_count"] for g in result["groups"]], [1, 2, 1])
        self.assertIsNone(result["spearman_rank_associations"]["top40_qualifying_count"]["canonical_recall_at_10"])
        self.assertEqual(result["spearman_rank_associations"]["top40_qualifying_count"]["query_median_ms"], 1)
        result = analysis.density_quality({0: sample[0]}, neighbors, truth, "legacy", 5)
        self.assertIsNone(result["groups"][1]["mean_returned_count"])
        self.assertEqual(result["groups"][1]["query_count"], 0)


class ContractTests(unittest.TestCase):
    def test_complete_and_ordered_partial_campaign(self):
        stages = contract_stages()
        self.assertTrue(analysis.check_campaign_contract(stages))
        for count in range(1, 4):
            self.assertFalse(analysis.check_campaign_contract(stages[:count]))
        for bad in ([], stages[::-1], stages[1:], [stages[0], stages[0]]):
            with self.assertRaises(ValueError):
                analysis.check_campaign_contract(bad)

    def test_same_queries_source_and_implementation(self):
        for field, value in (("queries", {"measured": [7]}), ("dataset_sha256", "wrong"),
                             ("source_file_sha256", {"runner": "wrong"})):
            stages = contract_stages()
            stages[-1][field] = value
            with self.assertRaises(ValueError):
                analysis.check_campaign_contract(stages)

    def test_metadata_same_scale_and_prefix_inheritance(self):
        for stage, field in ((2, "radial_labels_int16_le_sha256"),
                             (1, "prefix_100k_radial_labels_int16_le_sha256"),
                             (1, "prefix_100k_ordered_base_ids_int64_le_sha256"),
                             (1, "anchor_float64_le_sha256")):
            stages = contract_stages()
            stages[stage]["metadata"][field] = "mismatch"
            with self.assertRaises(ValueError):
                analysis.check_campaign_contract(stages)


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.run_path = cls.root / "synthetic-stage"
        cls.rows = fixture(cls.run_path)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def mock_verify(self):
        return patch.object(analysis, "verify_run", return_value={"passed": True, "run_id": self.run_path.name})

    def test_partial_analysis_grid_and_immutability(self):
        before = analysis.snapshot(self.run_path)
        with self.mock_verify() as proof:
            result = analysis.analyze([self.run_path])
        proof.assert_called_once_with(self.run_path.resolve())
        self.assertFalse(result["campaign_complete"])
        self.assertEqual(len(result["conditions"]), 30)
        self.assertEqual(len(result["metadata_comparisons"]), 15)
        self.assertEqual(result["counts"]["measured_executions"], 30000)
        c = next(c for c in result["metadata_comparisons"] if c["method"] == "hnsw_standard")
        self.assertAlmostEqual(c["paired_quality_deltas"]["canonical_recall_at_10"]["mean"], .2)
        self.assertIn("partial ordered campaign prefix", analysis.markdown(result))
        self.assertEqual(before, analysis.snapshot(self.run_path))

    def test_rejects_missing_mode_duplicate_and_wrong_identity(self):
        reader = analysis.read_rows
        bad_sets = [[r for r in self.rows if r["metadata_mode"] == "legacy"],
                    self.rows + [self.rows[0]], [{**self.rows[0], "scale_rows": 250000}] + self.rows[1:]]
        for bad in bad_sets:
            def changed(path):
                return bad if Path(path).name == "executions.jsonl" else reader(path)
            with self.mock_verify(), patch.object(analysis, "read_rows", side_effect=changed), self.assertRaises(ValueError):
                analysis.analyze([self.run_path])

    def test_fresh_independent_verification_failure_is_fatal(self):
        with patch.object(analysis, "verify_run", return_value={"passed": False}), self.assertRaises(ValueError):
            analysis.analyze([self.run_path])

    def test_requires_unique_stage_paths_and_output_exclusion(self):
        for paths in ([], [self.run_path]*2):
            with self.assertRaises(ValueError):
                analysis.analyze(paths)
        with self.assertRaises(FileExistsError):
            analysis.generate([self.run_path], self.run_path)
        with self.assertRaises(ValueError):
            analysis.generate([self.run_path], self.run_path / "output")
        with self.assertRaises(ValueError):
            analysis.generate([self.run_path], self.root / "raw_results" / "output")

    def test_checksum_change_rejected_after_analysis(self):
        with self.mock_verify():
            report = analysis.analyze([self.run_path])
        mutated = copy.deepcopy(report)
        mutated["provenance"]["inputs"][0]["sha256"]["executions.jsonl"] = "0"*64
        with self.assertRaises(ValueError):
            analysis.verify_inputs(mutated)
        mutated = copy.deepcopy(report)
        mutated["provenance"]["sources"][0]["sha256"] = "0"*64
        with self.assertRaises(ValueError):
            analysis.verify_inputs(mutated)

    def test_synthetic_figures_exclusive_output_and_manifest(self):
        output = self.root / "synthetic-analysis"
        before = analysis.snapshot(self.run_path)
        with self.mock_verify():
            report = analysis.generate([self.run_path], output)
        self.assertFalse(report["campaign_complete"])
        marker = analysis.read_json(output / "COMPLETE.json")
        self.assertFalse(marker["campaign_complete"])
        self.assertEqual(marker["completed_stages"], 1)
        self.assertEqual(marker["checksums_sha256"], analysis.sha256(output / "checksums.sha256"))
        for name in ("local_density.png", "quality_contrast.png", "paired_latency_ratio.png"):
            self.assertGreater((output / name).stat().st_size, 1000)
            self.assertEqual((output / name).read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        for line in (output / "checksums.sha256").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(digest, analysis.sha256(output / name))
        self.assertEqual(before, analysis.snapshot(self.run_path))
        with self.assertRaises(FileExistsError):
            analysis.generate([self.run_path], output)


if __name__ == "__main__":
    unittest.main()
