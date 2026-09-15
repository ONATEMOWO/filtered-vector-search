#!/usr/bin/env python3
"""Integration assertions for the loaded Milestone 1 database."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.run_smoke import (  # noqa: E402
    DIMENSIONS,
    EXPECTED_ROWS,
    FILTER_THRESHOLDS,
    K,
    explain_search,
    filter_counts,
    plan_details,
    run_psql,
    run_search,
)


def expect_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"ok: {label} = {actual}")


def main() -> None:
    extension = run_psql(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
    )
    if not extension:
        raise AssertionError("pgvector extension is not active")
    print(f"ok: pgvector extension active, version {extension}")

    row_count = int(run_psql("SELECT count(*) FROM smoke_items;"))
    query_count = int(run_psql("SELECT count(*) FROM smoke_queries;"))
    expect_equal(row_count, EXPECTED_ROWS, "smoke item row count")
    expect_equal(query_count, 5, "smoke query row count")

    dimension_check = run_psql(
        "SELECT min(vector_dims(embedding)), max(vector_dims(embedding)) FROM smoke_items;"
    )
    expect_equal(dimension_check, f"{DIMENSIONS}|{DIMENSIONS}", "vector dimensions")

    labels = run_psql(
        "SELECT count(DISTINCT source_label), min(source_label) FROM smoke_items;"
    )
    expect_equal(labels, "1|smoke-synthetic", "synthetic source label")

    counts = filter_counts()
    for threshold in FILTER_THRESHOLDS:
        expect_equal(
            counts[threshold],
            EXPECTED_ROWS * threshold // 100,
            f"rows matching filter_bucket < {threshold}",
        )

    dimensions_are_valid = run_psql(
        f"SELECT count(*) FROM smoke_items WHERE vector_dims(embedding) <> {DIMENSIONS};"
    )
    expect_equal(dimensions_are_valid, "0", "rows with invalid dimensions")

    indexes = run_psql(
        """
SELECT indexname
FROM pg_indexes
WHERE schemaname = 'public' AND tablename = 'smoke_items'
ORDER BY indexname;
"""
    ).splitlines()
    required_indexes = {
        "smoke_items_pkey",
        "smoke_items_embedding_hnsw",
    }
    missing = required_indexes.difference(indexes)
    if missing:
        raise AssertionError(f"missing indexes: {sorted(missing)}")
    print("ok: primary key and HNSW indexes exist")

    first_exact = run_search("exact", query_id=1, threshold=50, k=K)
    second_exact = run_search("exact", query_id=1, threshold=50, k=K)
    expect_equal(first_exact, second_exact, "exact top-k determinism")

    exact_plan = explain_search("exact", query_id=1, threshold=50, k=K)
    _, exact_nodes, exact_indexes = plan_details(exact_plan)
    if "smoke_items_embedding_hnsw" in exact_indexes:
        raise AssertionError("exact plan unexpectedly used the HNSW index")
    print(f"ok: exact plan does not use HNSW (nodes: {', '.join(exact_nodes)})")

    hnsw_plan = explain_search("hnsw", query_id=1, threshold=50, k=K)
    _, hnsw_nodes, hnsw_indexes = plan_details(hnsw_plan)
    if "smoke_items_embedding_hnsw" not in hnsw_indexes:
        raise AssertionError(
            f"HNSW plan did not use smoke_items_embedding_hnsw; indexes={hnsw_indexes}"
        )
    if "Index Scan" not in hnsw_nodes:
        raise AssertionError(f"HNSW plan has no Index Scan; nodes={hnsw_nodes}")
    print("ok: HNSW plan uses an Index Scan on smoke_items_embedding_hnsw")

    # pgvector defines its custom GUCs when the module is loaded in a backend.
    iterative_scan = run_psql("LOAD 'vector'; SHOW hnsw.iterative_scan;")
    expect_equal(iterative_scan, "off", "session default hnsw.iterative_scan")

    print("all database integration checks passed")


if __name__ == "__main__":
    main()
