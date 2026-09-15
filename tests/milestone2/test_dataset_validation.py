from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from experiments.milestone2.dataset import sha256_file, validate_hdf5


SHAPES = {
    "train": (4, 3),
    "test": (2, 3),
    "neighbors": (2, 2),
    "distances": (2, 2),
}


def write_fixture(
    path: Path,
    *,
    omit: str | None = None,
    train_dtype: object = np.float32,
    neighbor_dtype: object = np.int32,
    nonfinite: bool = False,
    out_of_range: bool = False,
    duplicate_neighbors: bool = False,
    distance_attribute: str = "euclidean",
) -> None:
    train = np.arange(12, dtype=train_dtype).reshape(4, 3)
    if nonfinite:
        train = train.astype(np.float32)
        train[0, 0] = np.nan
    test = np.arange(6, dtype=np.float32).reshape(2, 3)
    neighbors = np.asarray([[0, 1], [2, 3]], dtype=neighbor_dtype)
    if out_of_range:
        neighbors[1, 1] = 4
    if duplicate_neighbors:
        neighbors[0] = neighbors[0, 0]
    distances = np.asarray([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    values = {
        "train": train,
        "test": test,
        "neighbors": neighbors,
        "distances": distances,
    }
    with h5py.File(path, "w") as handle:
        handle.attrs["distance"] = distance_attribute
        for name, value in values.items():
            if name != omit:
                handle.create_dataset(name, data=value)


class Hdf5ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "tiny-sift.hdf5"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_tiny_fixture_records_contract_and_checksum(self) -> None:
        write_fixture(self.path)
        digest = sha256_file(self.path)
        result = validate_hdf5(
            self.path, expected_shapes=SHAPES, expected_sha256=digest
        )
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["sha256"], digest)
        self.assertEqual(result["groups"]["train"]["shape"], [4, 3])
        self.assertEqual(result["groups"]["train"]["dtype"], "float32")
        self.assertEqual(result["groups"]["neighbors"]["minimum_id"], 0)
        self.assertEqual(result["groups"]["neighbors"]["maximum_id"], 3)
        self.assertTrue(result["groups"]["neighbors"]["unique_within_query"])
        self.assertEqual(result["attributes"]["distance"], "euclidean")
        self.assertFalse(result["values_normalized"])

    def test_checksum_mismatch_is_rejected(self) -> None:
        write_fixture(self.path)
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            validate_hdf5(self.path, expected_shapes=SHAPES, expected_sha256="0" * 64)

    def test_missing_group_is_rejected(self) -> None:
        write_fixture(self.path, omit="neighbors")
        with self.assertRaisesRegex(ValueError, "missing required groups"):
            validate_hdf5(self.path, expected_shapes=SHAPES)

    def test_wrong_shape_is_rejected(self) -> None:
        write_fixture(self.path)
        wrong = dict(SHAPES)
        wrong["train"] = (5, 3)
        with self.assertRaisesRegex(ValueError, "shape mismatch"):
            validate_hdf5(self.path, expected_shapes=wrong)

    def test_nonfloat_vectors_are_rejected(self) -> None:
        write_fixture(self.path, train_dtype=np.int32)
        with self.assertRaisesRegex(ValueError, "floating-point vectors"):
            validate_hdf5(self.path, expected_shapes=SHAPES)

    def test_noninteger_neighbors_are_rejected(self) -> None:
        write_fixture(self.path, neighbor_dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "integer IDs"):
            validate_hdf5(self.path, expected_shapes=SHAPES)

    def test_nonfinite_vectors_are_rejected(self) -> None:
        write_fixture(self.path, nonfinite=True)
        with self.assertRaisesRegex(ValueError, "NaN or infinity"):
            validate_hdf5(self.path, expected_shapes=SHAPES)

    def test_out_of_range_neighbors_are_rejected(self) -> None:
        write_fixture(self.path, out_of_range=True)
        with self.assertRaisesRegex(ValueError, "outside zero-based base range"):
            validate_hdf5(self.path, expected_shapes=SHAPES)

    def test_duplicate_neighbors_are_rejected(self) -> None:
        write_fixture(self.path, duplicate_neighbors=True)
        with self.assertRaisesRegex(ValueError, "duplicate IDs"):
            validate_hdf5(self.path, expected_shapes=SHAPES)

    def test_wrong_distance_attribute_is_rejected(self) -> None:
        write_fixture(self.path, distance_attribute="angular")
        with self.assertRaisesRegex(ValueError, "distance='euclidean'"):
            validate_hdf5(self.path, expected_shapes=SHAPES)

    def test_missing_file_is_rejected(self) -> None:
        with self.assertRaises(FileNotFoundError):
            validate_hdf5(self.path, expected_shapes=SHAPES)


if __name__ == "__main__":
    unittest.main()
