#!/usr/bin/env python3
"""Run the Milestone 1 exact-versus-standard-HNSW smoke experiment."""

from __future__ import annotations

import csv
import json
import os
import statistics
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "raw_results"
EXPLAIN_DIR = RESULTS_DIR / "explain"
FILTER_THRESHOLDS = (50, 20, 10, 5, 1)
QUERY_IDS = (1, 2, 3, 4, 5)
K = 10
REPETITIONS = 5
WARMUPS = 1
EXPECTED_ROWS = 20_000
DIMENSIONS = 128
SEED = 20_260_915


EXACT_SETTINGS = (
    "SET LOCAL enable_indexscan = off;",
    "SET LOCAL enable_indexonlyscan = off;",
    "SET LOCAL enable_bitmapscan = off;",
    "SET LOCAL enable_seqscan = on;",
    "SET LOCAL jit = off;",
)

HNSW_SETTINGS = (
    "SET LOCAL enable_seqscan = off;",
    "SET LOCAL enable_bitmapscan = off;",
    "SET LOCAL hnsw.ef_search = 40;",
    "SET LOCAL hnsw.iterative_scan = 'off';",
    "SET LOCAL jit = off;",
)


def psql_command() -> list[str]:
    database = os.environ.get("PGDATABASE", "filtered_vector_search")
    if os.environ.get("USE_DOCKER") == "1":
        return [
            "docker",
            "compose",
            "-f",
            str(ROOT / "compose.yaml"),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-X",
            "-U",
            "postgres",
            "-d",
            database,
        ]

    pg_bin = Path(os.environ.get("PG_BIN", ROOT / ".runtime/postgres-17.11/bin"))
    executable = pg_bin / "psql"
    if not executable.is_file():
        raise RuntimeError(
            f"psql not found at {executable}; run make postgres-bootstrap or set PG_BIN"
        )
    return [str(executable), "-X", "-d", database]


def run_psql(sql: str) -> str:
    env = os.environ.copy()
    if os.environ.get("USE_DOCKER") != "1":
        env.setdefault("PGHOST", "127.0.0.1")
        env.setdefault("PGPORT", "55432")
        env.setdefault("PGUSER", os.environ.get("USER", "postgres"))
        env.setdefault("PGDATABASE", "filtered_vector_search")
    completed = subprocess.run(
        psql_command() + ["-v", "ON_ERROR_STOP=1", "-qAt", "-c", sql],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"psql failed ({completed.returncode})\nSQL:\n{sql}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout.strip()


def transaction(settings: Iterable[str], statement: str) -> str:
    return "\n".join(("BEGIN;", *settings, statement, "ROLLBACK;"))


def search_statement(method: str, query_id: int, threshold: int, k: int) -> str:
    tie_breaker = ", id" if method == "exact" else ""
    return f"""
SELECT id,
       embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = {query_id}) AS distance
FROM smoke_items
WHERE filter_bucket < {threshold}
ORDER BY embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = {query_id}){tie_breaker}
LIMIT {k};
""".strip()


def settings_for(method: str) -> tuple[str, ...]:
    if method == "exact":
        return EXACT_SETTINGS
    if method == "hnsw":
        return HNSW_SETTINGS
    raise ValueError(f"unknown method: {method}")


def run_search(method: str, query_id: int, threshold: int, k: int = K) -> list[tuple[int, float]]:
    output = run_psql(
        transaction(settings_for(method), search_statement(method, query_id, threshold, k))
    )
    if not output:
        return []
    rows: list[tuple[int, float]] = []
    for line in output.splitlines():
        record_id, distance = line.split("|", maxsplit=1)
        rows.append((int(record_id), float(distance)))
    return rows


def explain_search(method: str, query_id: int, threshold: int, k: int = K) -> list[dict[str, Any]]:
    statement = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + search_statement(
        method, query_id, threshold, k
    )
    return json.loads(run_psql(transaction(settings_for(method), statement)))


def recall_at_k(approximate_ids: Iterable[int], exact_ids: Iterable[int], k: int) -> float:
    """Intersection with exact top-k divided by available exact ground-truth size."""
    if k <= 0:
        raise ValueError("k must be positive")
    exact_top_k = list(exact_ids)[:k]
    if not exact_top_k:
        return 1.0 if not list(approximate_ids)[:k] else 0.0
    approximate_top_k = list(approximate_ids)[:k]
    return len(set(approximate_top_k).intersection(exact_top_k)) / len(exact_top_k)


def walk_plan(plan: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from walk_plan(child)


def plan_details(document: list[dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    root = document[0]["Plan"]
    nodes = list(walk_plan(root))
    node_types = [str(node.get("Node Type", "")) for node in nodes]
    index_names = [str(node["Index Name"]) for node in nodes if "Index Name" in node]
    return str(root.get("Node Type", "")), node_types, index_names


def database_environment() -> dict[str, Any]:
    output = run_psql(
        """
LOAD 'vector';
SELECT json_build_object(
  'server_version', current_setting('server_version'),
  'server_version_num', current_setting('server_version_num'),
  'pgvector_version', (SELECT extversion FROM pg_extension WHERE extname = 'vector'),
  'database', current_database(),
  'hnsw_ef_search_default', current_setting('hnsw.ef_search'),
  'hnsw_iterative_scan_default', current_setting('hnsw.iterative_scan')
);
"""
    )
    return json.loads(output)


def filter_counts() -> dict[int, int]:
    values = ",".join(f"({threshold})" for threshold in FILTER_THRESHOLDS)
    output = run_psql(
        f"""
SELECT threshold, count(*)
FROM (VALUES {values}) AS filters(threshold)
CROSS JOIN smoke_items
WHERE filter_bucket < threshold
GROUP BY threshold
ORDER BY threshold DESC;
"""
    )
    return {int(line.split("|")[0]): int(line.split("|")[1]) for line in output.splitlines()}


def write_filter_counts(counts: dict[int, int]) -> None:
    with (RESULTS_DIR / "filter_counts.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("filter_threshold", "condition", "qualifying_count", "match_rate"),
        )
        writer.writeheader()
        for threshold in FILTER_THRESHOLDS:
            writer.writerow(
                {
                    "filter_threshold": threshold,
                    "condition": f"filter_bucket < {threshold}",
                    "qualifying_count": counts[threshold],
                    "match_rate": f"{counts[threshold] / EXPECTED_ROWS:.6f}",
                }
            )


def write_summary(rows: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["method"]), int(row["filter_threshold"]))].append(row)

    fields = (
        "method",
        "filter_threshold",
        "target_selectivity",
        "samples",
        "median_latency_ms",
        "min_latency_ms",
        "max_latency_ms",
        "mean_recall_at_k",
        "returned_k_rate",
    )
    with (RESULTS_DIR / "smoke_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method in ("exact", "hnsw"):
            for threshold in FILTER_THRESHOLDS:
                group = groups[(method, threshold)]
                latencies = [float(row["latency_ms"]) for row in group]
                recalls = [float(row["recall_at_k"]) for row in group]
                returned = [bool(row["returned_k"]) for row in group]
                writer.writerow(
                    {
                        "method": method,
                        "filter_threshold": threshold,
                        "target_selectivity": f"{threshold / 100:.2f}",
                        "samples": len(group),
                        "median_latency_ms": f"{statistics.median(latencies):.6f}",
                        "min_latency_ms": f"{min(latencies):.6f}",
                        "max_latency_ms": f"{max(latencies):.6f}",
                        "mean_recall_at_k": f"{statistics.fmean(recalls):.6f}",
                        "returned_k_rate": f"{sum(returned) / len(returned):.6f}",
                    }
                )


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPLAIN_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).isoformat()
    environment = database_environment()
    environment.update(
        {
            "run_id": run_id,
            "dataset_label": "smoke-test synthetic data; not final research data",
            "row_count": EXPECTED_ROWS,
            "dimensions": DIMENSIONS,
            "seed": SEED,
            "query_count": len(QUERY_IDS),
            "k": K,
            "repetitions": REPETITIONS,
            "warmups_per_method_query_filter": WARMUPS,
            "distance": "Euclidean/L2 (<->)",
            "hnsw_index": {
                "operator_class": "vector_l2_ops",
                "m": 16,
                "ef_construction": 64,
                "ef_search": 40,
                "iterative_scan": "off",
            },
            "latency_measurement": "PostgreSQL EXPLAIN ANALYZE top-level Execution Time, milliseconds",
        }
    )
    (RESULTS_DIR / "environment.json").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8"
    )

    counts = filter_counts()
    write_filter_counts(counts)

    ground_truth: dict[tuple[int, int], list[int]] = {}
    for query_id in QUERY_IDS:
        for threshold in FILTER_THRESHOLDS:
            first = [row[0] for row in run_search("exact", query_id, threshold)]
            second = [row[0] for row in run_search("exact", query_id, threshold)]
            if first != second:
                raise RuntimeError(
                    f"exact results are not deterministic for query={query_id}, filter={threshold}"
                )
            if len(first) != K:
                raise RuntimeError(
                    f"exact search returned {len(first)} rows, expected {K}, "
                    f"query={query_id}, filter={threshold}"
                )
            ground_truth[(query_id, threshold)] = first

    rows: list[dict[str, Any]] = []
    representative_sql: list[str] = []
    for method in ("exact", "hnsw"):
        for threshold in FILTER_THRESHOLDS:
            for query_id in QUERY_IDS:
                for _ in range(WARMUPS):
                    run_search(method, query_id, threshold)
                for repetition in range(1, REPETITIONS + 1):
                    results = run_search(method, query_id, threshold)
                    document = explain_search(method, query_id, threshold)
                    ids = [row[0] for row in results]
                    distances = [row[1] for row in results]
                    recall = recall_at_k(ids, ground_truth[(query_id, threshold)], K)
                    top_node, node_types, index_names = plan_details(document)
                    if method == "exact" and "smoke_items_embedding_hnsw" in index_names:
                        raise RuntimeError("an exact-labeled execution used the HNSW index")
                    if method == "hnsw" and "smoke_items_embedding_hnsw" not in index_names:
                        raise RuntimeError(
                            "an HNSW-labeled execution did not use smoke_items_embedding_hnsw"
                        )
                    rows.append(
                        {
                            "run_id": run_id,
                            "dataset_label": "smoke-synthetic",
                            "row_count": EXPECTED_ROWS,
                            "dimensions": DIMENSIONS,
                            "seed": SEED,
                            "query_id": query_id,
                            "filter_threshold": threshold,
                            "filter_condition": f"filter_bucket < {threshold}",
                            "target_selectivity": f"{threshold / 100:.2f}",
                            "qualifying_count": counts[threshold],
                            "method": method,
                            "repetition": repetition,
                            "k": K,
                            "returned_count": len(ids),
                            "returned_k": len(ids) == K,
                            "recall_at_k": f"{recall:.6f}",
                            "latency_ms": f"{float(document[0]['Execution Time']):.6f}",
                            "result_ids": json.dumps(ids, separators=(",", ":")),
                            "distances": json.dumps(distances, separators=(",", ":")),
                            "plan_top_node": top_node,
                            "plan_node_types": json.dumps(node_types, separators=(",", ":")),
                            "plan_index_names": json.dumps(index_names, separators=(",", ":")),
                        }
                    )

                    if query_id == 1 and threshold in (50, 1) and repetition == 1:
                        plan_path = EXPLAIN_DIR / f"{method}_filter_{threshold}_query_1.json"
                        plan_path.write_text(
                            json.dumps(document, indent=2) + "\n", encoding="utf-8"
                        )
                        representative_sql.append(
                            f"-- {method}, query_id=1, filter_bucket < {threshold}\n"
                            + "\n".join(settings_for(method))
                            + "\nEXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)\n"
                            + search_statement(method, query_id, threshold, K)
                            + "\n"
                        )

    fields = tuple(rows[0].keys())
    with (RESULTS_DIR / "smoke_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    (EXPLAIN_DIR / "representative_queries.sql").write_text(
        "\n".join(representative_sql), encoding="utf-8"
    )
    write_summary(rows)
    print(f"wrote {len(rows)} measured executions to {RESULTS_DIR / 'smoke_results.csv'}")
    print(f"wrote representative plans to {EXPLAIN_DIR}")


if __name__ == "__main__":
    main()
