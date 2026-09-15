from __future__ import annotations

import unittest

from experiments.run_smoke import recall_at_k


class RecallAtKTests(unittest.TestCase):
    def test_perfect_recall_ignores_rank_order(self) -> None:
        self.assertEqual(recall_at_k([3, 2, 1], [1, 2, 3], 3), 1.0)

    def test_partial_overlap_uses_exact_top_k_denominator(self) -> None:
        self.assertEqual(recall_at_k([1, 8, 3, 9], [1, 2, 3, 4], 4), 0.5)

    def test_missing_approximate_rows_reduce_recall(self) -> None:
        self.assertEqual(recall_at_k([1, 2], [1, 2, 3, 4], 4), 0.5)

    def test_nonpositive_k_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            recall_at_k([1], [1], 0)


if __name__ == "__main__":
    unittest.main()

