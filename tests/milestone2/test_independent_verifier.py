"""Tamper cases for the read-only artifact verifier, independent of PostgreSQL."""

from __future__ import annotations

import copy
import unittest

import numpy as np

from experiments.milestone2.dataset import select_query_ids
from experiments.milestone2.metrics import validate_returned_results
from tests.milestone2.verify_run import (
    independent_summary,
    verify_query_selection,
    verify_result_fields,
    verify_source_distances,
)


class IndependentVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.buckets = {1: 0, 2: 0, 3: 1}
        self.row = {
            "result_ids": [1], "distances": [2.0],
            **validate_returned_results([1], [2.0], k=2, selected_buckets=self.buckets, threshold=1),
        }

    def test_correct_short_result_is_valid_but_incomplete(self) -> None:
        verify_result_fields(self.row, self.buckets, 1, 2)
        self.assertFalse(self.row["returned_k"])

    def test_false_completeness_claim_is_rejected(self) -> None:
        self.row["returned_k"] = True
        with self.assertRaisesRegex(AssertionError, "returned_k"):
            verify_result_fields(self.row, self.buckets, 1, 2)

    def test_false_count_claim_is_rejected(self) -> None:
        self.row["returned_count"] = 2
        with self.assertRaisesRegex(AssertionError, "returned_count"):
            verify_result_fields(self.row, self.buckets, 1, 2)

    def test_negative_and_nonfinite_distances_are_rejected(self) -> None:
        for value in (-1.0, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.row["distances"] = [value]
                with self.assertRaisesRegex(AssertionError, "invalid L2"):
                    verify_result_fields(self.row, self.buckets, 1, 2)

    def test_matching_false_validity_flags_do_not_excuse_bad_rows(self) -> None:
        self.row["result_ids"] = [3]
        self.row["filter_valid"] = False
        with self.assertRaisesRegex(AssertionError, "fail independent validation"):
            verify_result_fields(self.row, self.buckets, 1, 2)

    def test_integer_booleans_are_rejected(self) -> None:
        self.row["ids_unique"] = 1
        with self.assertRaisesRegex(AssertionError, "ids_unique"):
            verify_result_fields(self.row, self.buckets, 1, 2)

    def test_plausible_but_wrong_source_distance_is_rejected(self) -> None:
        vectors = np.array([[3.0, 4.0]], dtype=np.float32)
        row = {"result_ids": [7], "distances": [5.0]}
        verify_source_distances(row, np.zeros(2), vectors, {7: 0})
        row["distances"] = [4.0]
        with self.assertRaisesRegex(AssertionError, "canonical source-vector L2"):
            verify_source_distances(row, np.zeros(2), vectors, {7: 0})

    def test_deterministic_query_manifest_and_prefix(self) -> None:
        manifest = select_query_ids()
        manifest["qualification_timed_query_ids"] = manifest["measured_query_ids"][:5]
        verify_query_selection(manifest, {"timed_query_count": 5})
        changed = copy.deepcopy(manifest)
        changed["measured_query_ids"][0:2] = changed["measured_query_ids"][1::-1]
        changed["qualification_timed_query_ids"] = changed["measured_query_ids"][:5]
        with self.assertRaisesRegex(AssertionError, "deterministic reconstruction"):
            verify_query_selection(changed, {"timed_query_count": 5})
        manifest["qualification_timed_query_ids"] = manifest["measured_query_ids"][1:6]
        with self.assertRaisesRegex(AssertionError, "deterministic prefix"):
            verify_query_selection(manifest, {"timed_query_count": 5})

    def test_summary_reduces_each_query_before_condition(self) -> None:
        rows = []
        # Unequal repetition counts deliberately expose a pooled-execution median.
        for query_id, values in ((1, [1, 2, 9]), (2, [100])):
            for latency in values:
                rows.append({
                    "method": "hnsw_standard", "filter_threshold": 1,
                    "query_id": query_id, "duration_ns": latency,
                    "canonical_recall_at_10": 0.2 if query_id == 1 else 0.8,
                    "tie_aware_recall_at_10": 0.2 if query_id == 1 else 1.0,
                    "returned_k": query_id == 2, "error_type": None,
                })
        summary = independent_summary(rows)[0]
        self.assertEqual(summary["median_latency_ns"], 51)
        self.assertEqual(summary["p95_query_median_latency_ns"], 95)
        self.assertEqual(summary["query_samples"], 2)
        self.assertEqual(summary["mean_canonical_recall_at_10"], 0.5)
        self.assertEqual(summary["mean_tie_aware_recall_at_10"], 0.6)
        self.assertEqual(summary["returned_k_rate"], 0.25)


if __name__ == "__main__":
    unittest.main()
