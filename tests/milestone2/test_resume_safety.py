"""Regression coverage for evidence and environment gates added on resumption."""

from __future__ import annotations

import hashlib
import unittest

import numpy as np

from experiments.milestone2.database import source_stream_checksum
from experiments.milestone2.metrics import validate_returned_results
from experiments.milestone2.runner import verify_power_state


class SourceStreamChecksumTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ids = np.array([7, 11], dtype=np.int32)
        self.vectors = np.array([[1.0, -2.5], [0.25, 128.0]], dtype=np.float32)
        self.buckets = np.array([3, 4], dtype=np.int16)

    def test_source_hash_matches_explicit_pgvector_wire_fixture(self) -> None:
        # Each row starts with little-endian id/rank/bucket; vector_send then
        # uses a network-order dimension, reserved zero, and float32 values.
        wire_fixture = bytes.fromhex(
            "07000000 00000000 0300 0002 0000 3f800000 c0200000 "
            "0b000000 01000000 0400 0002 0000 3e800000 43000000"
        )
        self.assertEqual(
            source_stream_checksum(self.ids, self.vectors, self.buckets),
            hashlib.sha256(wire_fixture).hexdigest(),
        )

    def test_source_hash_is_independent_of_array_byte_order(self) -> None:
        self.assertEqual(
            source_stream_checksum(self.ids, self.vectors, self.buckets),
            source_stream_checksum(
                self.ids.astype(">i4"),
                self.vectors.astype(">f4"),
                self.buckets.astype(">i2"),
            ),
        )

    def test_source_hash_detects_id_metadata_vector_and_order_changes(self) -> None:
        expected = source_stream_checksum(self.ids, self.vectors, self.buckets)
        changed_ids = self.ids.copy()
        changed_ids[0] = 8
        changed_vectors = self.vectors.copy()
        changed_vectors[0, 1] = -2.0
        changed_buckets = self.buckets.copy()
        changed_buckets[0] = 2
        alternatives = (
            (changed_ids, self.vectors, self.buckets),
            (self.ids, changed_vectors, self.buckets),
            (self.ids, self.vectors, changed_buckets),
            (self.ids[::-1], self.vectors[::-1], self.buckets[::-1]),
        )
        for index, arrays in enumerate(alternatives):
            with self.subTest(change=index):
                self.assertNotEqual(expected, source_stream_checksum(*arrays))

    def test_source_hash_rejects_truncated_input_arrays(self) -> None:
        for arrays in (
            (self.ids[:1], self.vectors, self.buckets),
            (self.ids, self.vectors[:1], self.buckets),
            (self.ids, self.vectors, self.buckets[:1]),
        ):
            with self.subTest(lengths=tuple(map(len, arrays))):
                with self.assertRaises(ValueError):
                    source_stream_checksum(*arrays)


class PowerBoundaryTests(unittest.TestCase):
    def test_unchanged_ac_and_energy_settings_pass(self) -> None:
        before = {
            "ac_power_detected": True,
            "energy_settings_stdout": "AC Power:\n lowpowermode 0\n",
            "battery_stdout": "charge 80%",
        }
        # Battery charge may change without altering the selected energy mode.
        after = {**before, "battery_stdout": "charge 85%"}
        verify_power_state(before, after)

    def test_absent_ac_at_either_boundary_is_rejected(self) -> None:
        for before, after in ((False, True), (True, False), (False, False)):
            with self.subTest(before=before, after=after):
                with self.assertRaisesRegex(AssertionError, "AC power"):
                    verify_power_state(
                        {"ac_power_detected": before},
                        {"ac_power_detected": after},
                    )
        with self.assertRaisesRegex(AssertionError, "AC power"):
            verify_power_state({}, {"ac_power_detected": True})

    def test_changed_energy_settings_are_rejected(self) -> None:
        with self.assertRaisesRegex(AssertionError, "power settings changed"):
            verify_power_state(
                {"ac_power_detected": True, "energy_settings_stdout": "lowpowermode 0"},
                {"ac_power_detected": True, "energy_settings_stdout": "lowpowermode 1"},
            )


class DistanceValidityTests(unittest.TestCase):
    @staticmethod
    def validate(distances: list[float]) -> dict:
        ids = list(range(len(distances)))
        return validate_returned_results(
            ids,
            distances,
            k=10,
            selected_buckets={identifier: 0 for identifier in ids},
            threshold=1,
        )

    def test_single_nonfinite_or_negative_distance_is_rejected(self) -> None:
        # A singleton has no adjacent pair, so an ordering-only check misses it.
        for distance in (float("nan"), float("inf"), float("-inf"), -0.01):
            with self.subTest(distance=distance):
                result = self.validate([distance])
                self.assertFalse(result["distance_order_valid"])
                self.assertTrue(result["filter_valid"])

    def test_finite_nondecreasing_distances_including_ties_are_valid(self) -> None:
        result = self.validate([0.0, 1.25, 1.25, 9.0])
        self.assertTrue(result["distance_order_valid"])

    def test_decreasing_distances_remain_invalid(self) -> None:
        self.assertFalse(self.validate([2.0, 1.0])["distance_order_valid"])

    def test_empty_approximate_result_is_valid_but_incomplete(self) -> None:
        result = self.validate([])
        self.assertTrue(result["distance_order_valid"])
        self.assertFalse(result["returned_k"])
        self.assertEqual(result["shortfall"], 10)


if __name__ == "__main__":
    unittest.main()
