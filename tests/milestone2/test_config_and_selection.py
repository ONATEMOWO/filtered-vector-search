from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from experiments.milestone2.config import load_config, read_json, validate_config
from experiments.milestone2.dataset import (
    QUERY_DOMAIN,
    SCALE_DOMAIN,
    build_scale_manifest,
    deterministic_id_order,
    ensure_scale_order,
    select_query_ids,
    validate_source_manifest_identity,
)
from experiments.milestone2 import dataset
from experiments.milestone2.runner import build_schedule


ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config" / "milestone2"


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preflight = load_config(CONFIG_DIR / "preflight-10k.json")
        cls.qualification = load_config(CONFIG_DIR / "qualification-100k.json")

    def test_accepted_protocol_constants_are_frozen(self) -> None:
        protocol = self.preflight.protocol
        self.assertEqual(protocol["postgresql_version"], "17.11")
        self.assertEqual(protocol["pgvector_version"], "0.8.6")
        self.assertEqual(protocol["dimensions"], 128)
        self.assertEqual(protocol["distance"], "l2")
        self.assertEqual(protocol["k"], 10)
        self.assertEqual(protocol["filter_thresholds"], [50, 20, 10, 5, 1])
        self.assertEqual(
            protocol["methods"], ["exact", "hnsw_standard", "hnsw_iterative"]
        )
        self.assertEqual(protocol["final_scales"], [100_000, 250_000, 500_000, 1_000_000])

    def test_bounded_profiles_derive_expected_execution_counts(self) -> None:
        self.assertEqual(self.preflight.scale_rows, 10_000)
        self.assertEqual(self.preflight.measured_query_count, 5)
        self.assertEqual(self.preflight.repetitions, 1)
        self.assertEqual(self.preflight.rounds, 1)
        self.assertEqual(self.preflight.expected_execution_count, 75)
        self.assertEqual(
            self.preflight.expected_execution_count,
            self.preflight.stage["expected_timed_executions"],
        )

        self.assertEqual(self.qualification.scale_rows, 100_000)
        self.assertEqual(self.qualification.measured_query_count, 20)
        self.assertEqual(self.qualification.repetitions, 2)
        self.assertEqual(self.qualification.rounds, 1)
        self.assertEqual(self.qualification.expected_execution_count, 600)
        self.assertEqual(
            self.qualification.expected_execution_count,
            self.qualification.stage["expected_timed_executions"],
        )

    def test_profiles_generate_all_ground_truth_and_keep_warmups_disjoint(self) -> None:
        for config in (self.preflight, self.qualification):
            self.assertEqual(config.ground_truth_query_count, 200)
            self.assertEqual(config.warmup_query_count, 20)
            self.assertFalse(config.stage["full_benchmark_authorized"])

    def test_schedule_identity_includes_protocol_stage_round_and_scale(self) -> None:
        schedule = build_schedule(self.qualification, [7, 8, 9])
        self.assertEqual(schedule["protocol_id"], "milestone-2-sift1m-v1")
        self.assertEqual(schedule["stage_id"], "qualification-100k")
        self.assertEqual(schedule["scale_rows"], 100_000)
        self.assertEqual(schedule["rounds"], 1)
        self.assertEqual(len(schedule["blocks"]), 15)
        for block in schedule["blocks"]:
            domain = block["block_schedule_domain"]
            self.assertIn("milestone-2-sift1m-v1", domain)
            self.assertIn("qualification-100k", domain)
            self.assertIn("|1|100000", domain)
            self.assertEqual(block["round"], 1)
            self.assertEqual(block["scale_rows"], 100_000)

    def test_config_rejects_expensive_or_unaccepted_stage_changes(self) -> None:
        protocol = self.preflight.protocol
        mutations = (
            {"scale_rows": 100_000},
            {"scale_rows": 250_000},
            {"timed_query_count": 0},
            {"timed_query_count": 4},
            {"timed_query_count": 21},
            {"repetitions": 0},
            {"repetitions": 2},
            {"repetitions": 3},
            {"rounds": 2},
            {"full_benchmark_authorized": True},
            {"ground_truth_query_count": 199},
            {"warmup_query_count": 19},
            {"independent_validation_count": 19},
            {"independent_validation_count": 21},
            {"stop_after_stage": False},
            {"record_resource_projection": False},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                stage = copy.deepcopy(self.preflight.stage)
                stage.update(mutation)
                with self.assertRaises(ValueError):
                    validate_config(protocol, stage)

    def test_config_rejects_protocol_drift(self) -> None:
        protocol = copy.deepcopy(self.preflight.protocol)
        protocol["k"] = 20
        with self.assertRaises(ValueError):
            validate_config(protocol, self.preflight.stage)

    def test_json_loader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"session":{"mode":"a","mode":"b"}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                read_json(path)


class DeterministicSelectionTests(unittest.TestCase):
    def test_scale_order_matches_independent_known_sha256_fixture(self) -> None:
        order = deterministic_id_order(10, SCALE_DOMAIN)
        self.assertEqual(order.tolist(), [4, 5, 0, 2, 6, 3, 9, 8, 7, 1])
        self.assertEqual(order.dtype, np.dtype("int32"))

    def test_query_order_matches_independent_known_sha256_fixture(self) -> None:
        order = deterministic_id_order(10, QUERY_DOMAIN)
        self.assertEqual(order.tolist(), [1, 7, 0, 6, 9, 8, 5, 2, 3, 4])

    def test_query_selection_is_deterministic_unique_and_disjoint(self) -> None:
        first = select_query_ids()
        second = select_query_ids()
        self.assertEqual(first, second)
        measured = first["measured_query_ids"]
        warmup = first["warmup_query_ids"]
        self.assertEqual(len(measured), 200)
        self.assertEqual(len(warmup), 20)
        self.assertEqual(len(set(measured)), 200)
        self.assertEqual(len(set(warmup)), 20)
        self.assertTrue(set(measured).isdisjoint(warmup))
        self.assertTrue(first["sets_disjoint"])
        self.assertTrue(all(0 <= value < 10_000 for value in measured + warmup))

    def test_scale_membership_is_nested_and_bucketed_by_rank(self) -> None:
        order = deterministic_id_order(300, SCALE_DOMAIN)
        small = build_scale_manifest(order, 100, [50, 20, 10, 5, 1])
        large = build_scale_manifest(order, 200, [50, 20, 10, 5, 1])
        np.testing.assert_array_equal(
            small["selected_base_ids"], large["selected_base_ids"][:100]
        )
        np.testing.assert_array_equal(
            small["filter_buckets"], np.arange(100, dtype=np.int32) % 100
        )
        self.assertEqual(
            small["filter_counts"], {"50": 50, "20": 20, "10": 10, "5": 5, "1": 1}
        )

    def test_filter_counts_are_exact_for_every_declared_scale(self) -> None:
        thresholds = [50, 20, 10, 5, 1]
        for scale in (10_000, 100_000, 250_000, 500_000, 1_000_000):
            with self.subTest(scale=scale):
                buckets = np.arange(scale, dtype=np.int32) % 100
                observed = {
                    threshold: int(np.count_nonzero(buckets < threshold))
                    for threshold in thresholds
                }
                expected = {threshold: scale * threshold // 100 for threshold in thresholds}
                self.assertEqual(observed, expected)

    def test_invalid_selection_sizes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            deterministic_id_order(0, SCALE_DOMAIN)
        with self.assertRaises(ValueError):
            select_query_ids(query_count=10, measured_count=8, warmup_count=3)

    def test_cached_scale_order_is_digest_and_permutation_checked(self) -> None:
        expected_order = deterministic_id_order(10, SCALE_DOMAIN)
        expected_ids_sha = hashlib.sha256(
            expected_order.astype("<i4", copy=False).tobytes()
        ).hexdigest()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            dataset, "GENERATED_DIR", Path(directory)
        ), patch.object(dataset, "ROOT", Path(directory)):
            first, manifest = ensure_scale_order(
                10, expected_ordered_ids_sha256=expected_ids_sha
            )
            np.testing.assert_array_equal(first, expected_order)
            second, _ = ensure_scale_order(
                10,
                expected_ordered_ids_sha256=expected_ids_sha,
                expected_cache_sha256=manifest["cache_sha256"],
            )
            np.testing.assert_array_equal(second, expected_order)
            cache_path = Path(directory) / "scale_order_10.npy"
            altered = expected_order.copy()
            altered[[0, 1]] = altered[[1, 0]]
            with cache_path.open("wb") as handle:
                np.save(handle, altered, allow_pickle=False)
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                ensure_scale_order(
                    10,
                    expected_ordered_ids_sha256=expected_ids_sha,
                    expected_cache_sha256=manifest["cache_sha256"],
                )

    def test_source_manifest_matches_frozen_protocol(self) -> None:
        protocol = load_config(CONFIG_DIR / "preflight-10k.json").protocol
        source = json.loads(
            (ROOT / "data" / "sift1m" / "source_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(
            validate_source_manifest_identity(source, protocol["dataset"])["passed"]
        )
        changed = copy.deepcopy(source)
        changed["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_source_manifest_identity(changed, protocol["dataset"])


if __name__ == "__main__":
    unittest.main()
