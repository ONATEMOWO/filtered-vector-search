"""Protocol invariants; no database or benchmark artifacts are touched."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.preparation.protocol import (
    FILTERS, METHODS, PROTOCOL, build_schedule, config_sha256, load_protocol,
)


class ProtocolTests(unittest.TestCase):
    def test_checked_in_profile_matches_code(self):
        self.assertEqual(load_protocol(), PROTOCOL)
        self.assertEqual(len(config_sha256(PROTOCOL)), 64)

    def assert_rejected(self, config):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                load_protocol(path)

    def test_no_scale_or_budget_expansion(self):
        for key, value in (("scale_rows", 250000), ("repetitions", 6),
                           ("measured_query_count", 20), ("expected_measured_executions", 0)):
            with self.subTest(key=key):
                self.assert_rejected({**PROTOCOL, key: value})

    def test_no_type_coercion_or_unknown_fields(self):
        self.assert_rejected({**PROTOCOL, "k": 10.0})
        self.assert_rejected({**PROTOCOL, "os_cache_flushed": 0})
        self.assert_rejected({**PROTOCOL, "new_option": "silently ignored"})

    def test_no_arm_or_reset_substitution(self):
        config = copy.deepcopy(PROTOCOL)
        config["arms_by_build"]["2"] = ["A", "B"]
        self.assert_rejected(config)
        self.assert_rejected({**PROTOCOL, "reset_policy": "none"})

    def test_schedule_reproducible_and_independent_of_input_order(self):
        ids = list(range(200))
        self.assertEqual(build_schedule(PROTOCOL, ids), build_schedule(PROTOCOL, ids[::-1]))

    def test_counterbalance_and_complete_conditions(self):
        first, second = build_schedule(PROTOCOL, list(range(200)))["builds"]
        self.assertEqual(first["arms"], ["A", "B"])
        self.assertEqual(second["arms"], ["B", "A"])
        keys = lambda b: [(x["method"], x["filter_threshold"]) for x in b["blocks"]]
        self.assertEqual(keys(first), keys(second)[::-1])
        self.assertEqual(set(keys(first)), {(m, t) for m in METHODS for t in FILTERS})
        self.assertEqual(len(first["blocks"]), 15)

    def test_paired_arms_cannot_get_different_schedules(self):
        # Arms reference a single build schedule; no arm-specific random domain.
        for build in build_schedule(PROTOCOL, list(range(200)))["builds"]:
            common = build["blocks"][0]["query_order_by_repetition"]
            for block in build["blocks"]:
                self.assertEqual(block["query_order_by_repetition"], common)
                self.assertEqual(len(common), 5)
                self.assertTrue(all(sorted(order) == list(range(200)) for order in common))
                self.assertEqual(sorted(block["exposure_query_order"]), list(range(200)))

    def test_bad_query_ids_rejected(self):
        for ids in (list(range(199)), list(range(199)) + [0],
                    list(range(199)) + [True], list(range(199)) + [10000]):
            with self.assertRaises(ValueError):
                build_schedule(PROTOCOL, ids)

    def test_no_schedule_for_unfrozen_configuration(self):
        with self.assertRaises(ValueError):
            build_schedule({**PROTOCOL, "repetitions": 4}, list(range(200)))


if __name__ == "__main__":
    unittest.main()
