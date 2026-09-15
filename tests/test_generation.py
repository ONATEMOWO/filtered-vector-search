from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from data.generate_smoke_data import generate


class SmokeDataGenerationTests(unittest.TestCase):
    def test_generation_is_deterministic_and_balanced(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir)
            second = Path(second_dir)
            generate(rows=200, dimensions=4, queries=2, seed=1234, output_dir=first)
            generate(rows=200, dimensions=4, queries=2, seed=1234, output_dir=second)

            first_metadata = json.loads((first / "generation_metadata.json").read_text())
            second_metadata = json.loads((second / "generation_metadata.json").read_text())
            self.assertEqual(first_metadata["files"], second_metadata["files"])
            self.assertEqual(set(first_metadata["bucket_counts"].values()), {2})

            with (first / "smoke_items.csv").open(newline="") as handle:
                first_row = next(csv.DictReader(handle))
            dimensions = len(first_row["embedding"].strip("[]").split(","))
            self.assertEqual(dimensions, 4)
            self.assertEqual(first_row["source_label"], "smoke-synthetic")


if __name__ == "__main__":
    unittest.main()

