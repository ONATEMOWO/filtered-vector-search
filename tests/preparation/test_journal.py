from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.preparation.journal import CheckpointJournal


class JournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "ACTIVE").touch()
        self.journal = CheckpointJournal(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def rows(start: int = 1, phase: str = "measured") -> list[dict]:
        return [{"phase": phase, "sequence_index": start + offset} for offset in range(2)]

    def test_complete_pass_is_exclusive_and_consolidates_in_order(self) -> None:
        self.journal.capture("one.jsonl", "measured", self.rows())
        self.journal.capture("two.jsonl", "measured", self.rows(3))
        rows = self.journal.consolidate({"measured"}, "executions.jsonl")
        self.assertEqual([row["sequence_index"] for row in rows], [1, 2, 3, 4])
        self.assertEqual(len(self.journal.chunks), 2)
        with self.assertRaises(FileExistsError):
            self.journal.capture("one.jsonl", "measured", self.rows())
        with self.assertRaises(FileExistsError):
            self.journal.consolidate({"measured"}, "executions.jsonl")

    def test_interruption_preserves_prior_and_partial_pass(self) -> None:
        self.journal.capture("one.jsonl", "measured", self.rows())
        def interrupted():
            yield {"phase": "measured", "sequence_index": 3}
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.journal.capture("two.jsonl", "measured", interrupted())
        self.assertTrue((self.root / "one.jsonl").is_file())
        self.assertFalse((self.root / "two.jsonl").exists())
        partial = [json.loads(line) for line in (self.root / "two.partial.jsonl").read_text().splitlines()]
        self.assertEqual(partial, [{"phase": "measured", "sequence_index": 3}])
        self.assertEqual(len(self.journal.chunks), 1)

    def test_mutation_prevents_consolidation(self) -> None:
        self.journal.capture("one.jsonl", "measured", self.rows())
        (self.root / "one.jsonl").write_text("{}\n")
        with self.assertRaisesRegex(AssertionError, "changed"):
            self.journal.consolidate({"measured"}, "executions.jsonl")
        self.assertFalse((self.root / "executions.jsonl").exists())

    def test_phase_and_path_validation(self) -> None:
        with self.assertRaises(ValueError):
            self.journal.capture("../escape.jsonl", "measured", self.rows())
        with self.assertRaisesRegex(AssertionError, "phase"):
            self.journal.capture("one.jsonl", "other", self.rows())
        with self.assertRaises(AssertionError):
            self.journal.capture("empty.jsonl", "measured", [])

    def test_preparation_separate_and_duplicate_sequences_rejected(self) -> None:
        self.journal.capture("warm.jsonl", "disjoint_warmup", self.rows(1, "disjoint_warmup"))
        self.journal.capture("timed.jsonl", "measured", self.rows(3))
        self.assertEqual(len(self.journal.consolidate({"measured"}, "executions.jsonl")), 2)
        self.journal.capture("duplicate.jsonl", "measured", self.rows(3))
        with self.assertRaisesRegex(AssertionError, "duplicate"):
            self.journal.consolidate({"measured"}, "bad.jsonl")

    def test_finalized_run_cannot_receive_checkpoint(self) -> None:
        (self.root / "COMPLETE.json").write_text("{}")
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            self.journal.capture("one.jsonl", "measured", self.rows())


if __name__ == "__main__":
    unittest.main()
