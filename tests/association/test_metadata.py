"""Small synthetic invariants only; no SIFT experiment or PostgreSQL access."""

import copy
import json
import unittest

import numpy as np

from experiments.association.metadata import (
    _density_summary,
    _permuted_labels,
    association_diagnostics,
    build_metadata,
    neighborhoods,
)


def fixture(count=1000):
    ids = np.arange(count, dtype=np.int32)[::-1]
    vectors = np.zeros((count, 128), dtype=np.float32)
    vectors[:, 0] = np.arange(count) % 100
    return ids, vectors, np.zeros(128, dtype=np.float32)


class MetadataTests(unittest.TestCase):
    def test_balanced_deterministic_and_json_manifest(self):
        ids, vectors, anchor = fixture()
        first, manifest = build_metadata(ids, vectors, anchor)
        second, repeated = build_metadata(ids, vectors, anchor)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(manifest, repeated)
        self.assertEqual(first.dtype, np.dtype("int16"))
        np.testing.assert_array_equal(first, np.arange(1000) % 100)
        self.assertEqual(manifest["filter_counts"], {"50": 500, "20": 200, "10": 100, "5": 50, "1": 10})
        json.dumps(manifest, allow_nan=False)

    def test_all_ties_use_base_id_and_preserve_input_order(self):
        ids, vectors, anchor = fixture(200)
        labels, manifest = build_metadata(ids, vectors * 0, anchor)
        np.testing.assert_array_equal(labels.reshape(2, 100), np.tile(np.arange(100)[::-1], (2, 1)))
        self.assertEqual(manifest["score_boundary_summary_by_filter"]["5"]["boundary_tied_block_count"], 2)

    def test_labels_inherit_every_complete_block_prefix(self):
        ids, vectors, anchor = fixture(1200)
        vectors[:, 0] = np.random.default_rng(4).normal(size=1200)
        all_labels, _ = build_metadata(ids, vectors, anchor)
        for count in (100, 200, 1000):
            prefix, _ = build_metadata(ids[:count], vectors[:count], anchor)
            np.testing.assert_array_equal(prefix, all_labels[:count])

    def test_rejects_invalid_ids_shapes_and_nonfinite_vectors(self):
        ids, vectors, anchor = fixture(100)
        for bad in (ids[:-1], ids.astype(float), np.zeros(100, dtype=int), -ids - 1, np.ones(100, dtype=bool)):
            with self.subTest(kind="ids", dtype=bad.dtype, count=len(bad)):
                with self.assertRaises(ValueError):
                    build_metadata(bad, vectors, anchor)
        for bad in (vectors[:, :127], vectors + np.nan, vectors.astype(complex), vectors.astype(str)):
            with self.assertRaises(ValueError):
                build_metadata(ids, bad, anchor)
        for bad in (anchor[:127], anchor + np.inf, anchor.astype(bool)):
            with self.assertRaises(ValueError):
                build_metadata(ids, vectors, bad)

    def test_squared_distance_overflow_rejected(self):
        ids, vectors, anchor = fixture(100)
        with self.assertRaisesRegex(ValueError, "overflowed"):
            build_metadata(ids, np.full(vectors.shape, 1e300), anchor)


class NeighborhoodTests(unittest.TestCase):
    def setUp(self):
        self.ids, self.vectors, self.anchor = fixture()
        self.legacy = np.arange(1000) % 100
        self.radial, _ = build_metadata(self.ids, self.vectors, self.anchor)

    def make_records(self):
        queries = {9: self.anchor.copy(), 3: self.anchor.copy()}
        queries[9][0] = 99
        return neighborhoods(self.ids, self.vectors, queries, self.legacy, self.radial, anchor=self.anchor)

    def test_exact_neighbors_ties_counts_and_anchor(self):
        records = self.make_records()
        self.assertEqual([r["query_id"] for r in records], [3, 9])
        first = records[0]
        self.assertEqual(first["neighbor_ids"][:10], list(range(99, 1000, 100)))
        self.assertEqual(first["squared_distances"][:10], [0.0] * 10)
        self.assertEqual(first["local_counts"]["radial"]["5"], {"40": 40, "100": 50, "1000": 50})
        self.assertEqual(records[1]["query_anchor_distance"], 99.0)
        json.dumps(records, allow_nan=False)

    def test_all_tied_neighborhood_selects_lowest_ids(self):
        ids, vectors, anchor = fixture(1100)
        vectors *= 0
        radial, _ = build_metadata(ids, vectors, anchor)
        records = neighborhoods(ids, vectors, {0: anchor}, np.arange(1100) % 100, radial)
        self.assertEqual(records[0]["neighbor_ids"], list(range(1000)))
        self.assertNotIn("query_anchor_distance", records[0])

    def test_rejects_bad_query_and_labels_and_small_scale(self):
        for query_map in ({}, {True: self.anchor}, {-1: self.anchor}, {0: self.anchor + np.nan}):
            with self.assertRaises(ValueError):
                neighborhoods(self.ids, self.vectors, query_map, self.legacy, self.radial)
        with self.assertRaises(ValueError):
            neighborhoods(self.ids, self.vectors, {0: self.anchor}, self.legacy[::-1], self.radial)
        with self.assertRaises(ValueError):
            neighborhoods(self.ids, self.vectors, {0: self.anchor}, self.legacy, np.zeros(1000, dtype=int))
        with self.assertRaises(ValueError):
            neighborhoods(self.ids[:100], self.vectors[:100], {0: self.anchor}, self.legacy[:100], self.radial[:100])


class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ids, cls.vectors, cls.anchor = fixture()
        # Within-block ordering is deliberately scrambled while radial distance
        # remains interpretable; this is only a synthetic manipulation fixture.
        rng = np.random.default_rng(41)
        for block in cls.vectors.reshape(10, 100, 128):
            block[:, 0] = rng.permutation(100)
        cls.radial, _ = build_metadata(cls.ids, cls.vectors, cls.anchor)
        cls.records = neighborhoods(
            cls.ids, cls.vectors,
            {i: np.asarray([float(i)] + [0.0] * 127) for i in (0, 25, 50, 75, 99)},
            np.arange(1000) % 100, cls.radial,
        )

    def diagnostics(self, records=None, **kwargs):
        return association_diagnostics(self.records if records is None else records, self.ids, self.radial, [0, 25, 50, 75], permutations=9, **kwargs)

    def test_permutations_preserve_every_block_and_are_not_one_shared_shuffle(self):
        first = _permuted_labels(1000, np.random.Generator(np.random.PCG64(3)))
        second = _permuted_labels(1000, np.random.Generator(np.random.PCG64(3)))
        np.testing.assert_array_equal(first, second)
        np.testing.assert_array_equal(np.sort(first.reshape(10, 100), axis=1), np.tile(np.arange(100), (10, 1)))
        self.assertFalse(np.array_equal(first[:100], first[100:200]))

    def test_diagnostics_deterministic_and_exclude_warmups(self):
        result = self.diagnostics()
        self.assertEqual(result, self.diagnostics())
        self.assertEqual(result["groups"]["measured"]["query_ids"], [0, 25, 50, 75])
        self.assertEqual(result["groups"]["warmup"]["query_ids"], [99])
        self.assertEqual(result["permutation_null"]["replicates"], 9)
        for threshold in ("50", "20", "10", "5", "1"):
            values = result["primary_by_filter"][threshold]["permutation_D"]
            self.assertEqual(len(values), 9)
            self.assertEqual(result["primary_by_filter"][threshold]["permutation_D_p95_linear"], float(np.quantile(values, 0.95, method="linear")))
        json.dumps(result, allow_nan=False)

    def test_gate_uses_both_required_filters_and_both_strict_comparisons(self):
        result = self.diagnostics()
        self.assertTrue(result["gate_passed"])
        conditions = result["primary_by_filter"]
        self.assertEqual(result["gate_passed"], all(conditions[t]["radial_D"] > conditions[t]["legacy_D"] and conditions[t]["radial_D"] > conditions[t]["permutation_D_p95_linear"] for t in ("50", "5")))
        equal_records = copy.deepcopy(self.records)
        equal_radial = np.arange(1000) % 100
        for record in equal_records:
            record["local_counts"]["radial"] = copy.deepcopy(record["local_counts"]["legacy"])
        equal = association_diagnostics(equal_records, self.ids, equal_radial, [0, 25, 50, 75], permutations=9)
        self.assertFalse(equal["gate_passed"])

    def test_complete_depletion_is_not_zero_deviation(self):
        summary = _density_summary(np.zeros(4, dtype=int), 100, 5)
        self.assertEqual(summary["variance_local_fraction"], 0.0)
        self.assertAlmostEqual(summary["D_mean_squared_deviation_from_global"], 0.0025)
        self.assertAlmostEqual(summary["D_mean_squared_deviation_from_global"], summary["variance_local_fraction"] + summary["squared_mean_displacement"])

    def test_rejects_bad_replicates_seed_query_sets_and_unknown_neighbors(self):
        for kwargs in ({"seed": -1}, {"seed": True}):
            with self.assertRaises(ValueError):
                self.diagnostics(**kwargs)
        for measured in ([], [0, 0], [12345], [True]):
            with self.assertRaises(ValueError):
                association_diagnostics(self.records, self.ids, self.radial, measured, permutations=9)
        for count in (0, True, 2.5):
            with self.assertRaises(ValueError):
                association_diagnostics(self.records, self.ids, self.radial, [0], permutations=count)
        corrupted = copy.deepcopy(self.records)
        corrupted[0]["neighbor_ids"][-1] = 5000
        with self.assertRaises(ValueError):
            self.diagnostics(corrupted)

    def test_stored_counts_and_canonical_order_cannot_be_fabricated(self):
        corrupted = copy.deepcopy(self.records)
        corrupted[0]["local_counts"]["radial"]["5"]["100"] += 1
        with self.assertRaisesRegex(ValueError, "local counts"):
            self.diagnostics(corrupted)
        corrupted = copy.deepcopy(self.records)
        corrupted[0]["local_counts"]["radial"]["5"]["100"] = float(corrupted[0]["local_counts"]["radial"]["5"]["100"])
        with self.assertRaisesRegex(ValueError, "JSON integers"):
            self.diagnostics(corrupted)
        corrupted = copy.deepcopy(self.records)
        corrupted[0]["neighbor_ids"][:2] = corrupted[0]["neighbor_ids"][:2][::-1]
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.diagnostics(corrupted)
        with self.assertRaisesRegex(ValueError, "unique"):
            self.diagnostics(self.records + self.records[:1])


if __name__ == "__main__":
    unittest.main()
