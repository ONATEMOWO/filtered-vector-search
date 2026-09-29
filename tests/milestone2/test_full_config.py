"""The resumed authorization is limited to two separately built 100k rounds."""

import copy
from pathlib import Path
import unittest

from experiments.milestone2.config import load_config, validate_config
from experiments.milestone2.runner import build_schedule


CONFIG = Path(__file__).resolve().parents[2] / "config" / "milestone2"


class Full100kConfigurationTests(unittest.TestCase):
    def test_counts_and_rounds_are_explicit_and_separate(self):
        for round_number in (1, 2):
            config = load_config(CONFIG / f"benchmark-100k-round-{round_number}.json")
            self.assertTrue(config.is_full_benchmark)
            self.assertEqual(config.round_numbers, (round_number,))
            self.assertEqual(config.rounds, 1)
            self.assertEqual(config.expected_execution_count, 15000)
            self.assertEqual(config.ground_truth_query_count, 200)
            self.assertEqual(config.warmup_query_count, 20)
            self.assertFalse(config.protocol["final_execution"]["authorized"])

    def test_full_profiles_reject_validation_reduction_and_scope_expansion(self):
        config = load_config(CONFIG / "benchmark-100k-round-2.json")
        for mutation in (
            {"scale_rows": 250000}, {"scale_rows": 500000}, {"scale_rows": 1000000},
            {"stage_id": "benchmark-250k-round-2"}, {"rounds": 2},
            {"experiment_round": 1}, {"timed_query_count": 20},
            {"repetitions": 2}, {"independent_validation_count": 19},
            {"warmup_query_count": 5}, {"ground_truth_query_count": 20},
            {"larger_scales_authorized": True}, {"expected_timed_executions": 600},
            {"cache_reset_method": "pg_buffercache_evict_after_checkpoint"},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                stage = copy.deepcopy(config.stage)
                stage.update(mutation)
                validate_config(config.protocol, stage)

    def test_qualification_round_cannot_be_spoofed(self):
        config = load_config(CONFIG / "qualification-100k.json")
        self.assertFalse(config.is_full_benchmark)
        self.assertEqual(config.round_numbers, (1,))
        stage = {**config.stage, "experiment_round": 2}
        with self.assertRaises(ValueError):
            validate_config(config.protocol, stage)

    def test_separate_rounds_have_full_unique_schedules(self):
        schedules = []
        for round_number in (1, 2):
            config = load_config(CONFIG / f"benchmark-100k-round-{round_number}.json")
            schedule = build_schedule(config, list(range(200)))
            self.assertEqual(len(schedule["blocks"]), 15)
            keys = set()
            for block in schedule["blocks"]:
                self.assertEqual(block["round"], round_number)
                self.assertEqual(len(block["query_order_by_repetition"]), 5)
                for repetition, queries in enumerate(block["query_order_by_repetition"], 1):
                    self.assertEqual(sorted(queries), list(range(200)))
                    keys.update((round_number, block["method"], block["filter_threshold"],
                                 query, repetition) for query in queries)
            self.assertEqual(len(keys), 15000)
            schedules.append(schedule)
        self.assertNotEqual(schedules[0]["blocks"], schedules[1]["blocks"])


if __name__ == "__main__":
    unittest.main()
