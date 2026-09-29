from __future__ import annotations

import copy
import unittest

from experiments.milestone2.ground_truth import (
    ground_truth_index,
    ground_truth_sql,
    make_ground_truth_record,
    select_validation_keys,
)
from experiments.milestone2.metrics import (
    canonical_recall_at_k,
    tie_aware_recall_at_k,
    validate_returned_results,
)


def ground_truth_record() -> dict[str, object]:
    return make_ground_truth_record(
        run_id="test-run",
        scale_rows=100,
        threshold=50,
        qualifying_count=50,
        query_id=7,
        k=3,
        rows=[(12, 1.0), (11, 0.5), (14, 1.0), (13, 1.0)],
        dataset_sha256="a" * 64,
        scale_manifest_sha256="b" * 64,
    )


class RecallTests(unittest.TestCase):
    def test_canonical_recall_is_order_independent(self) -> None:
        self.assertEqual(canonical_recall_at_k([3, 2, 1], [1, 2, 3], 3), 1.0)

    def test_canonical_recall_uses_fixed_k_denominator_for_missing_rows(self) -> None:
        self.assertEqual(canonical_recall_at_k([1, 2], [1, 2, 3, 4], 4), 0.5)

    def test_canonical_recall_rejects_short_ground_truth(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 4"):
            canonical_recall_at_k([1, 2], [1, 2, 3], 4)

    def test_canonical_recall_rejects_duplicate_results(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            canonical_recall_at_k([1, 1, 2], [1, 2, 3], 3)

    def test_tie_aware_recall_credits_an_interchangeable_boundary_neighbor(self) -> None:
        approximate = [1, 2, 3, 4, 5, 6, 7, 8, 11, 99]
        closer = list(range(1, 9))
        ties = [9, 10, 11]
        self.assertEqual(tie_aware_recall_at_k(approximate, closer, ties, 10), 0.9)
        self.assertEqual(
            canonical_recall_at_k(approximate, list(range(1, 11)), 10), 0.8
        )

    def test_tie_aware_recall_does_not_credit_non_tied_rows(self) -> None:
        self.assertEqual(tie_aware_recall_at_k([1, 2, 99], [1, 2], [3, 4], 4), 0.5)

    def test_tie_partition_must_be_disjoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "disjoint"):
            tie_aware_recall_at_k([1], [1], [1, 2], 3)


class ReturnedResultValidationTests(unittest.TestCase):
    def test_complete_valid_result(self) -> None:
        result = validate_returned_results(
            [1, 2], [0.1, 0.2], k=2, selected_buckets={1: 0, 2: 4}, threshold=5
        )
        self.assertEqual(result["returned_count"], 2)
        self.assertTrue(result["returned_k"])
        self.assertEqual(result["shortfall"], 0)
        self.assertTrue(result["ids_unique"])
        self.assertTrue(result["scale_valid"])
        self.assertTrue(result["filter_valid"])
        self.assertTrue(result["distance_order_valid"])

    def test_missing_rows_are_valid_but_incomplete(self) -> None:
        result = validate_returned_results(
            [1], [0.1], k=2, selected_buckets={1: 0}, threshold=5
        )
        self.assertFalse(result["returned_k"])
        self.assertEqual(result["shortfall"], 1)
        self.assertTrue(result["filter_valid"])

    def test_invalid_filter_scale_duplicates_and_order_are_detected(self) -> None:
        duplicate = validate_returned_results(
            [1, 1], [0.1, 0.2], k=2, selected_buckets={1: 0}, threshold=5
        )
        self.assertFalse(duplicate["ids_unique"])
        outside = validate_returned_results(
            [2], [0.1], k=2, selected_buckets={1: 0}, threshold=5
        )
        self.assertFalse(outside["scale_valid"])
        self.assertFalse(outside["filter_valid"])
        filtered = validate_returned_results(
            [1], [0.1], k=2, selected_buckets={1: 5}, threshold=5
        )
        self.assertFalse(filtered["filter_valid"])
        unordered = validate_returned_results(
            [1, 2], [0.2, 0.1], k=2, selected_buckets={1: 0, 2: 0}, threshold=5
        )
        self.assertFalse(unordered["distance_order_valid"])


class GroundTruthTests(unittest.TestCase):
    def test_record_is_canonical_and_preserves_boundary_ties(self) -> None:
        record = ground_truth_record()
        self.assertEqual(record["canonical_ids"], [11, 12, 13])
        self.assertEqual(record["canonical_distances"], [0.5, 1.0, 1.0])
        self.assertEqual(record["strictly_closer_ids"], [11])
        self.assertEqual(record["boundary_tie_ids"], [12, 13, 14])
        self.assertEqual(record["all_with_ties_ids"], [11, 12, 13, 14])
        self.assertEqual(
            record["generation_method"],
            "PostgreSQL exact filtered L2 search on milestone2.sift_exact with no vector index",
        )
        self.assertEqual(record["generation_sql"], ground_truth_sql(50, 3))

    def test_ground_truth_sql_uses_distance_only_for_with_ties(self) -> None:
        statement = ground_truth_sql(5, 10)
        self.assertIn("ORDER BY distance FETCH FIRST 10 ROWS WITH TIES", statement)
        self.assertNotIn("ORDER BY distance, id", statement)

    def test_ground_truth_checksum_round_trip_and_mutation_detection(self) -> None:
        record = ground_truth_record()
        indexed = ground_truth_index([record])
        self.assertIs(indexed[(7, 50)], record)
        mutated = copy.deepcopy(record)
        mutated["canonical_ids"] = [999, 12, 13]
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            ground_truth_index([mutated])

    def test_duplicate_ground_truth_key_is_rejected(self) -> None:
        record = ground_truth_record()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ground_truth_index([record, copy.deepcopy(record)])

    def test_short_exact_result_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected at least"):
            make_ground_truth_record(
                run_id="test",
                scale_rows=100,
                threshold=1,
                qualifying_count=1,
                query_id=1,
                k=2,
                rows=[(1, 0.0)],
                dataset_sha256="a" * 64,
                scale_manifest_sha256="b" * 64,
            )

    def test_validation_key_selection_is_deterministic_and_bounded(self) -> None:
        first = select_validation_keys(range(10), [50, 20, 10, 5, 1], 20)
        second = select_validation_keys(range(10), [50, 20, 10, 5, 1], 20)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 20)
        self.assertEqual(len(set(first)), 20)
        counts = {threshold: 0 for threshold in (50, 20, 10, 5, 1)}
        for _, threshold in first:
            counts[threshold] += 1
        self.assertEqual(set(counts.values()), {4})

    def test_validation_key_selection_rejects_invalid_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "negative"):
            select_validation_keys(range(2), [50], -1)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            select_validation_keys(range(2), [50], 3)


if __name__ == "__main__":
    unittest.main()
