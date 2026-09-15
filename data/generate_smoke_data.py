#!/usr/bin/env python3
"""Generate deterministic synthetic vectors for Milestone 1 pipeline checks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path


DEFAULT_ROWS = 20_000
DEFAULT_DIMENSIONS = 128
DEFAULT_QUERIES = 5
DEFAULT_SEED = 20_260_915


def vector_literal(rng: random.Random, dimensions: int) -> str:
    """Return an L2-normalized pgvector literal with stable decimal formatting."""
    values = [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in values))
    return "[" + ",".join(f"{value / norm:.8f}" for value in values) + "]"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generate(rows: int, dimensions: int, queries: int, seed: int, output_dir: Path) -> None:
    if rows < 100:
        raise ValueError("rows must be at least 100 so all filter buckets are represented")
    if dimensions <= 0 or queries <= 0:
        raise ValueError("dimensions and queries must be positive")

    output_dir.mkdir(parents=True, exist_ok=True)
    item_path = output_dir / "smoke_items.csv"
    query_path = output_dir / "smoke_queries.csv"
    metadata_path = output_dir / "generation_metadata.json"

    rng = random.Random(seed)
    buckets = [index % 100 for index in range(rows)]
    rng.shuffle(buckets)

    with item_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "filter_bucket", "source_label", "embedding"])
        for offset, bucket in enumerate(buckets, start=1):
            writer.writerow(
                [offset, bucket, "smoke-synthetic", vector_literal(rng, dimensions)]
            )

    # Continue the same seeded PRNG stream after item generation. These query
    # vectors are independent of (and therefore not rows copied from) smoke_items.
    with query_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["query_id", "embedding"])
        for query_id in range(1, queries + 1):
            writer.writerow([query_id, vector_literal(rng, dimensions)])

    bucket_counts = {str(bucket): buckets.count(bucket) for bucket in range(100)}
    metadata = {
        "label": "smoke-test synthetic data; not the final research dataset",
        "rows": rows,
        "query_count": queries,
        "dimensions": dimensions,
        "seed": seed,
        "prng": "Python random.Random (MT19937)",
        "vector_method": (
            "independent Uniform[-1,1] components, L2-normalized, formatted to 8 decimals"
        ),
        "metadata_method": (
            "repeat buckets 0..99, then shuffle with the same seeded PRNG; "
            "filter_bucket < N approximates N percent"
        ),
        "filter_thresholds": [50, 20, 10, 5, 1],
        "bucket_counts": bucket_counts,
        "files": {
            item_path.name: {"sha256": sha256(item_path)},
            query_path.name: {"sha256": sha256(query_path)},
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {rows} item vectors to {item_path}")
    print(f"wrote {queries} query vectors to {query_path}")
    print(f"seed={seed}, dimensions={dimensions}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS)
    parser.add_argument("--queries", type=int, default=DEFAULT_QUERIES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    args = parser.parse_args()
    generate(args.rows, args.dimensions, args.queries, args.seed, args.output_dir)


if __name__ == "__main__":
    main()

