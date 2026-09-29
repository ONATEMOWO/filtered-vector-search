"""SIFT1M validation, deterministic sampling, and scale construction."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import h5py
import numpy as np

from .config import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[2]
SIFT_DIR = ROOT / "data" / "sift1m"
DEFAULT_HDF5_PATH = ROOT / ".runtime" / "datasets" / "sift-128-euclidean.hdf5"
SOURCE_MANIFEST_PATH = SIFT_DIR / "source_manifest.json"
LOCAL_MANIFEST_PATH = SIFT_DIR / "local_manifest.json"
GENERATED_DIR = ROOT / "data" / "generated" / "milestone2"
SCALE_DOMAIN = "sift-base-v1|"
QUERY_DOMAIN = "sift-query-v1|"
EXPECTED_SHAPES = {
    "train": (1_000_000, 128),
    "test": (10_000, 128),
    "neighbors": (10_000, 100),
    "distances": (10_000, 100),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_id(domain: str, identifier: int) -> bytes:
    return hashlib.sha256(f"{domain}{identifier}".encode("utf-8")).digest()


def deterministic_id_order(count: int, domain: str) -> np.ndarray:
    if count <= 0:
        raise ValueError("count must be positive")
    ranked = [(hash_id(domain, identifier), identifier) for identifier in range(count)]
    ranked.sort(key=lambda value: (value[0], value[1]))
    return np.fromiter((identifier for _, identifier in ranked), dtype=np.int32, count=count)


def _validate_scale_order(
    order: np.ndarray,
    base_count: int,
    *,
    expected_ordered_ids_sha256: str | None,
) -> str:
    if order.dtype != np.dtype(np.int32) or order.shape != (base_count,):
        raise ValueError(
            f"scale order must have dtype int32 and shape ({base_count},), "
            f"got dtype={order.dtype} shape={order.shape}"
        )
    minimum = int(np.min(order))
    maximum = int(np.max(order))
    if minimum != 0 or maximum != base_count - 1:
        raise ValueError(
            f"scale order IDs must span [0, {base_count - 1}], got [{minimum}, {maximum}]"
        )
    if not np.array_equal(np.sort(order), np.arange(base_count, dtype=np.int32)):
        raise ValueError("scale order is not a permutation of every zero-based base ID")
    ordered_ids_sha256 = hashlib.sha256(
        order.astype("<i4", copy=False).tobytes()
    ).hexdigest()
    if (
        expected_ordered_ids_sha256 is not None
        and ordered_ids_sha256 != expected_ordered_ids_sha256
    ):
        raise ValueError(
            "scale order digest mismatch: "
            f"expected {expected_ordered_ids_sha256}, got {ordered_ids_sha256}"
        )
    return ordered_ids_sha256


def ensure_scale_order(
    base_count: int = 1_000_000,
    *,
    expected_ordered_ids_sha256: str | None = None,
    expected_cache_sha256: str | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    order_path = GENERATED_DIR / f"scale_order_{base_count}.npy"
    if order_path.exists():
        cache_sha256 = sha256_file(order_path)
        if expected_cache_sha256 is not None and cache_sha256 != expected_cache_sha256:
            raise ValueError(
                "cached scale order file checksum mismatch: "
                f"expected {expected_cache_sha256}, got {cache_sha256}"
            )
        order = np.load(order_path, allow_pickle=False)
    else:
        order = deterministic_id_order(base_count, SCALE_DOMAIN)
        _validate_scale_order(
            order,
            base_count,
            expected_ordered_ids_sha256=expected_ordered_ids_sha256,
        )
        temporary = order_path.with_suffix(".npy.part")
        with temporary.open("wb") as handle:
            np.save(handle, order, allow_pickle=False)
        cache_sha256 = sha256_file(temporary)
        if expected_cache_sha256 is not None and cache_sha256 != expected_cache_sha256:
            temporary.unlink(missing_ok=True)
            raise ValueError(
                "generated scale order cache checksum mismatch: "
                f"expected {expected_cache_sha256}, got {cache_sha256}"
            )
        temporary.replace(order_path)
    ordered_ids_sha256 = _validate_scale_order(
        order,
        base_count,
        expected_ordered_ids_sha256=expected_ordered_ids_sha256,
    )
    return order, {
        "algorithm": "ascending SHA-256 digest, then ascending base_id",
        "domain": SCALE_DOMAIN,
        "base_count": base_count,
        "zero_based_scale_rank": True,
        "cache_path": str(order_path.relative_to(ROOT)),
        "cache_sha256": cache_sha256,
        "expected_cache_sha256": expected_cache_sha256,
        "cache_checksum_valid": expected_cache_sha256 is None
        or cache_sha256 == expected_cache_sha256,
        "ordered_ids_sha256": ordered_ids_sha256,
        "expected_ordered_ids_sha256": expected_ordered_ids_sha256,
        "ordered_ids_checksum_valid": expected_ordered_ids_sha256 is None
        or ordered_ids_sha256 == expected_ordered_ids_sha256,
        "range_valid": True,
        "permutation_valid": True,
    }


def validate_source_manifest_identity(
    source_manifest: dict[str, Any], dataset_protocol: dict[str, Any]
) -> dict[str, Any]:
    """Require the checked-in source manifest to match the frozen protocol identity."""
    if not isinstance(source_manifest, dict):
        raise ValueError("SIFT1M source manifest must be a JSON object")
    if not isinstance(dataset_protocol, dict):
        raise ValueError("frozen dataset protocol must be a JSON object")

    failures: list[str] = []

    def check(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            failures.append(f"{label}: expected {expected!r}, got {actual!r}")

    check("canonical_url", source_manifest.get("canonical_url"), dataset_protocol.get("source_url"))
    check("byte_size", source_manifest.get("byte_size"), dataset_protocol.get("expected_bytes"))
    check("sha256", source_manifest.get("sha256"), dataset_protocol.get("expected_sha256"))
    check(
        "values_normalized",
        source_manifest.get("values_normalized"),
        dataset_protocol.get("normalize_vectors"),
    )

    protocol_shapes = dataset_protocol.get("expected_shapes", {})
    check("expected_base_shape", source_manifest.get("expected_base_shape"), protocol_shapes.get("base"))
    check(
        "expected_query_shape",
        source_manifest.get("expected_query_shape"),
        protocol_shapes.get("queries"),
    )
    check(
        "expected_neighbor_shape",
        source_manifest.get("expected_neighbor_shape"),
        protocol_shapes.get("neighbors"),
    )

    protocol_keys = dataset_protocol.get("keys", {})
    protocol_dtypes = dataset_protocol.get("expected_dtypes", {})
    validated_groups = source_manifest.get("validated_groups", {})
    for logical_name in ("base", "queries", "neighbors", "distances"):
        group_name = protocol_keys.get(logical_name)
        group = validated_groups.get(group_name, {}) if group_name is not None else {}
        check(
            f"validated_groups.{group_name}.shape",
            group.get("shape"),
            protocol_shapes.get(logical_name),
        )
        check(
            f"validated_groups.{group_name}.dtype",
            group.get("dtype"),
            protocol_dtypes.get(logical_name),
        )

    if failures:
        raise ValueError(
            "SIFT1M source manifest does not match the frozen protocol: "
            + "; ".join(failures)
        )
    return {
        "passed": True,
        "source_manifest_sha256": hashlib.sha256(
            canonical_json_bytes(source_manifest)
        ).hexdigest(),
        "checked_fields": [
            "canonical_url",
            "byte_size",
            "sha256",
            "values_normalized",
            "expected shapes",
            "validated group shapes and dtypes",
        ],
    }


def select_query_ids(
    query_count: int = 10_000, measured_count: int = 200, warmup_count: int = 20
) -> dict[str, Any]:
    if measured_count + warmup_count > query_count:
        raise ValueError("requested query sets exceed available queries")
    order = deterministic_id_order(query_count, QUERY_DOMAIN)
    measured = [int(value) for value in order[:measured_count]]
    warmup = [int(value) for value in order[measured_count : measured_count + warmup_count]]
    return {
        "algorithm": "ascending SHA-256 digest, then ascending query_id",
        "domain": QUERY_DOMAIN,
        "available_query_count": query_count,
        "measured_query_ids": measured,
        "warmup_query_ids": warmup,
        "measured_count": measured_count,
        "warmup_count": warmup_count,
        "sets_disjoint": set(measured).isdisjoint(warmup),
        "selection_sha256": hashlib.sha256(
            np.asarray(measured + warmup, dtype="<i4").tobytes()
        ).hexdigest(),
    }


def _all_finite(dataset: h5py.Dataset, chunk_rows: int = 16_384) -> bool:
    for start in range(0, dataset.shape[0], chunk_rows):
        values = dataset[start : start + chunk_rows]
        if not np.isfinite(values).all():
            return False
    return True


def validate_hdf5(
    path: Path,
    *,
    expected_shapes: dict[str, tuple[int, ...]] | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    shapes = expected_shapes or EXPECTED_SHAPES
    if not path.is_file():
        raise FileNotFoundError(path)
    observed_sha256 = sha256_file(path)
    if expected_sha256 and observed_sha256 != expected_sha256:
        raise ValueError(
            f"SIFT1M checksum mismatch: expected {expected_sha256}, got {observed_sha256}"
        )

    groups: dict[str, Any] = {}
    with h5py.File(path, "r") as handle:
        missing = sorted(set(shapes).difference(handle.keys()))
        if missing:
            raise ValueError(f"SIFT HDF5 is missing required groups: {missing}")
        for name, expected_shape in shapes.items():
            dataset = handle[name]
            observed_shape = tuple(int(value) for value in dataset.shape)
            if observed_shape != tuple(expected_shape):
                raise ValueError(
                    f"{name} shape mismatch: expected {expected_shape}, got {observed_shape}"
                )
            if name in {"train", "test", "distances"} and not np.issubdtype(
                dataset.dtype, np.floating
            ):
                raise ValueError(f"{name} must contain floating-point vectors")
            if name == "neighbors" and not np.issubdtype(dataset.dtype, np.integer):
                raise ValueError("neighbors must contain integer IDs")
            if expected_shapes is None:
                expected_dtype = np.dtype("<i4") if name == "neighbors" else np.dtype("<f4")
                if dataset.dtype != expected_dtype:
                    raise ValueError(
                        f"{name} dtype mismatch: expected {expected_dtype}, got {dataset.dtype}"
                    )
            finite = True
            if name in {"train", "test", "distances"}:
                finite = _all_finite(dataset)
                if not finite:
                    raise ValueError(f"{name} contains NaN or infinity")
            groups[name] = {
                "shape": list(observed_shape),
                "dtype": str(dataset.dtype),
                "finite": finite,
            }

        neighbors = handle["neighbors"]
        minimum = int(np.min(neighbors))
        maximum = int(np.max(neighbors))
        if minimum < 0 or maximum >= shapes["train"][0]:
            raise ValueError(
                f"neighbor IDs outside zero-based base range: min={minimum}, max={maximum}"
            )
        groups["neighbors"].update(
            {"minimum_id": minimum, "maximum_id": maximum, "zero_based_range_valid": True}
        )
        neighbors_unique = True
        for start in range(0, neighbors.shape[0], 1_024):
            block = np.asarray(neighbors[start : start + 1_024])
            ordered = np.sort(block, axis=1)
            if np.any(ordered[:, 1:] == ordered[:, :-1]):
                neighbors_unique = False
                break
        if not neighbors_unique:
            raise ValueError("a supplied neighbor row contains duplicate IDs")
        groups["neighbors"]["unique_within_query"] = True
        distance_set = handle["distances"]
        distances_nonnegative = True
        distances_nondecreasing = True
        for start in range(0, distance_set.shape[0], 1_024):
            block = np.asarray(distance_set[start : start + 1_024])
            distances_nonnegative = distances_nonnegative and bool(np.all(block >= 0))
            distances_nondecreasing = distances_nondecreasing and bool(
                np.all(block[:, 1:] >= block[:, :-1])
            )
        if not distances_nonnegative or not distances_nondecreasing:
            raise ValueError("supplied neighbor distances are negative or not ordered")
        groups["distances"].update(
            {"nonnegative": True, "nondecreasing_within_query": True}
        )
        distance_attribute = handle.attrs.get("distance")
        if isinstance(distance_attribute, bytes):
            distance_attribute = distance_attribute.decode("utf-8")
        if distance_attribute != "euclidean":
            raise ValueError(f"expected HDF5 distance='euclidean', got {distance_attribute!r}")
        sentinel: dict[str, Any] | None = None
        if expected_shapes is None:
            sentinel_neighbor = int(handle["neighbors"][0, 0])
            sentinel_distance = float(handle["distances"][0, 0])
            direct_distance = float(
                np.linalg.norm(
                    np.asarray(handle["test"][0], dtype=np.float32)
                    - np.asarray(handle["train"][sentinel_neighbor], dtype=np.float32)
                )
            )
            if sentinel_neighbor != 932_085 or not np.isclose(
                sentinel_distance, direct_distance, rtol=1e-6, atol=1e-5
            ):
                raise ValueError("SIFT1M zero-based neighbor/distance sentinel validation failed")
            sentinel = {
                "query_id": 0,
                "neighbor_rank": 0,
                "neighbor_id": sentinel_neighbor,
                "supplied_distance": sentinel_distance,
                "recomputed_float32_l2": direct_distance,
                "passed": True,
            }

    return {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "path": str(path),
        "byte_size": path.stat().st_size,
        "sha256": observed_sha256,
        "groups": groups,
        "attributes": {"distance": "euclidean"},
        "zero_based_sentinel": sentinel,
        "values_normalized": False,
        "base_ids_zero_based": True,
        "validation_passed": True,
    }


def build_scale_manifest(order: np.ndarray, scale_rows: int, thresholds: Iterable[int]) -> dict[str, Any]:
    if scale_rows <= 0 or scale_rows > len(order):
        raise ValueError("scale_rows is outside the global ranking")
    selected = order[:scale_rows].astype(np.int32, copy=True)
    ranks = np.arange(scale_rows, dtype=np.int32)
    buckets = (ranks % 100).astype(np.int16)
    threshold_list = [int(value) for value in thresholds]
    counts = {str(value): int(np.count_nonzero(buckets < value)) for value in threshold_list}
    for threshold in threshold_list:
        expected = scale_rows * threshold // 100
        if counts[str(threshold)] != expected:
            raise AssertionError(
                f"filter_bucket < {threshold}: expected {expected}, got {counts[str(threshold)]}"
            )
    membership_bytes = b"".join(
        (
            selected.astype("<i4", copy=False).tobytes(),
            ranks.astype("<i4", copy=False).tobytes(),
            buckets.astype("<i2", copy=False).tobytes(),
        )
    )
    return {
        "scale_rows": scale_rows,
        "rank_zero_based": True,
        "selection": f"first {scale_rows} IDs in global {SCALE_DOMAIN!r} SHA-256 order",
        "filter_bucket_formula": "scale_rank mod 100",
        "selected_base_ids_sha256": hashlib.sha256(
            selected.astype("<i4", copy=False).tobytes()
        ).hexdigest(),
        "membership_sha256": hashlib.sha256(membership_bytes).hexdigest(),
        "filter_counts": counts,
        "selected_base_ids": selected,
        "scale_ranks": ranks,
        "filter_buckets": buckets,
    }


def serializable_scale_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if not isinstance(value, np.ndarray)}


def load_scale_vectors(path: Path, selected_base_ids: np.ndarray) -> np.ndarray:
    """Read the source sequentially and place selected vectors in scale-rank order."""
    selected_base_ids = np.asarray(selected_base_ids, dtype=np.int32)
    id_to_rank = np.full(EXPECTED_SHAPES["train"][0], -1, dtype=np.int32)
    id_to_rank[selected_base_ids] = np.arange(len(selected_base_ids), dtype=np.int32)
    vectors = np.empty((len(selected_base_ids), EXPECTED_SHAPES["train"][1]), dtype=np.float32)
    found = 0
    with h5py.File(path, "r") as handle:
        source = handle["train"]
        for start in range(0, source.shape[0], 16_384):
            stop = min(start + 16_384, source.shape[0])
            ranks = id_to_rank[start:stop]
            mask = ranks >= 0
            if np.any(mask):
                block = np.asarray(source[start:stop], dtype=np.float32)
                vectors[ranks[mask]] = block[mask]
                found += int(np.count_nonzero(mask))
    if found != len(selected_base_ids):
        raise AssertionError(f"loaded {found} selected vectors, expected {len(selected_base_ids)}")
    return vectors


def load_query_vectors(path: Path, query_ids: Iterable[int]) -> dict[int, np.ndarray]:
    ids = [int(value) for value in query_ids]
    with h5py.File(path, "r") as handle:
        all_queries = np.asarray(handle["test"], dtype=np.float32)
    return {query_id: all_queries[query_id].copy() for query_id in ids}


def write_local_manifest(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(canonical_json_bytes(value))
    temporary.replace(path)
