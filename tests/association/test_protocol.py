import copy
import json
import unittest
from experiments.association.protocol import (
    PROTOCOL, ROOT, STAGES, config_digest, schedule, stage_config, validate_config,
)


class ProtocolTests(unittest.TestCase):
    def test_checked_in_protocol_matches_implementation(self):
        self.assertEqual(json.loads((ROOT / "config/metadata-association-v1.json").read_text()), PROTOCOL)

    def test_only_four_stages_and_strict_types(self):
        for scale, build in STAGES:
            validate_config(stage_config(scale, build))
        for scale, build in ((10000, 1), (500000, 1), (100000, 3), (100000.0, 1), (100000, True)):
            with self.assertRaises(ValueError):
                stage_config(scale, build)

    def test_no_profile_mutation_or_extra_options(self):
        for key, value in (("repetitions", 4), ("hnsw_ef_search", 80), ("extra", True),
                           ("scale_rows", 100000.0)):
            altered = stage_config(100000, 1)
            altered[key] = value
            with self.assertRaises(ValueError):
                validate_config(altered)
        altered = stage_config(100000, 1)
        altered["stop_after_stages"] = 1
        with self.assertRaises(ValueError):
            validate_config(altered)

    def test_deterministic_matched_scales_and_modes(self):
        queries = list(range(200))
        first = schedule(stage_config(100000, 1), queries)
        self.assertEqual(first, schedule(stage_config(250000, 1), queries))
        self.assertEqual(first, schedule(stage_config(100000, 1), list(reversed(queries))))
        self.assertEqual(first["modes"], ["legacy", "radial"])
        self.assertEqual(len(first["blocks"]), 15)
        for block in first["blocks"]:
            self.assertEqual(len(block["query_order_by_repetition"]), 5)
            for order in block["query_order_by_repetition"]:
                self.assertEqual(sorted(order), queries)
        second = schedule(stage_config(100000, 2), queries)
        self.assertEqual(second["modes"], ["radial", "legacy"])
        key = lambda b: (b["method"], b["filter_threshold"])
        self.assertEqual(list(map(key, second["blocks"])), list(reversed(list(map(key, first["blocks"])))))

    def test_schedule_rejects_missing_duplicate_wrong_type_query(self):
        for queries in (list(range(199)), [0] * 200, [True]+list(range(1,200)),
                        [0.0]+list(range(1,200)), [-1]+list(range(1,200)),
                        [10000]+list(range(1,200))):
            with self.assertRaises(ValueError):
                schedule(stage_config(100000, 1), queries)

    def test_digest_canonical_and_distinct_stages(self):
        config = stage_config(100000, 1)
        reversed_keys = dict(reversed(list(config.items())))
        self.assertEqual(config_digest(config), config_digest(reversed_keys))
        self.assertEqual(len({config_digest(stage_config(*stage)) for stage in STAGES}), 4)
        self.assertEqual(config, copy.deepcopy(config))


if __name__ == "__main__":
    unittest.main()
