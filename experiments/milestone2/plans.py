"""Untimed EXPLAIN capture and strict method-routing assertions."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any

import numpy as np
import psycopg
from psycopg import sql

from .database import HNSW_INDEX, search_parameters, search_sql, session_settings


def walk_plan(node: dict[str, Any], path: str = "Plan") -> Iterable[tuple[str, dict[str, Any]]]:
    yield path, node
    for index, child in enumerate(node.get("Plans", [])):
        yield from walk_plan(child, f"{path}.Plans[{index}]")


def _text_values(node: dict[str, Any], keys: Iterable[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = node.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return values


def verify_plan_document(
    *,
    method: str,
    threshold: int,
    document: list[dict[str, Any]],
    observed_settings: dict[str, str],
    fetched_result_count: int | None = None,
) -> dict[str, Any]:
    if not document or "Plan" not in document[0]:
        raise AssertionError("EXPLAIN JSON has no root plan")
    root = document[0]["Plan"]
    nodes_with_paths = list(walk_plan(root))
    nodes = [node for _, node in nodes_with_paths]
    node_types = [str(node.get("Node Type", "")) for node in nodes]
    index_names = [str(node["Index Name"]) for node in nodes if "Index Name" in node]
    relations = [str(node["Relation Name"]) for node in nodes if "Relation Name" in node]
    failures: list[str] = []
    expected_settings = {
        "jit": "off",
        "plan_cache_mode": "force_generic_plan",
        "statement_timeout": "2min",
    }

    vector_order_evidence = [
        text
        for node in nodes
        for text in _text_values(node, ("Order By", "Sort Key"))
        if "<->" in text and "embedding" in text
    ]
    if not vector_order_evidence:
        failures.append("plan has no vector-distance ordering evidence")

    hnsw_path: str | None = None
    hnsw_node: dict[str, Any] | None = None
    hnsw_actual_rows: int | None = None
    hnsw_actual_loops: int | None = None
    if method == "exact":
        expected_settings.update(
            {name: "on" for name in (
                "enable_seqscan", "enable_bitmapscan", "enable_indexscan", "enable_indexonlyscan"
            )}
        )
        if "sift_exact" not in relations:
            failures.append("exact plan does not read sift_exact")
        if HNSW_INDEX in index_names or any("hnsw" in value.lower() for value in index_names):
            failures.append("exact plan used a vector/HNSW index")
    elif method in {"hnsw_standard", "hnsw_iterative"}:
        for path, node in nodes_with_paths:
            if node.get("Index Name") == HNSW_INDEX:
                hnsw_path, hnsw_node = path, node
                break
        if hnsw_node is None:
            failures.append(f"HNSW plan did not use {HNSW_INDEX}")
        else:
            if hnsw_node.get("Node Type") != "Index Scan":
                failures.append("HNSW access is not the required Index Scan")
            if hnsw_node.get("Relation Name") != "sift_hnsw":
                failures.append("HNSW index scan is not on sift_hnsw")
            order_text = " ".join(_text_values(hnsw_node, ("Order By",)))
            if "<->" not in order_text or "embedding" not in order_text:
                failures.append("HNSW scan lacks vector-distance Order By")
            filter_text = str(hnsw_node.get("Filter", ""))
            threshold_pattern = rf"filter_bucket\s*<\s*{threshold}(?!\d)"
            if "filter_bucket" not in filter_text or not re.search(
                threshold_pattern, filter_text
            ):
                failures.append("metadata predicate is not a filter on the HNSW scan")
            hnsw_actual_rows = int(hnsw_node.get("Actual Rows", -1))
            hnsw_actual_loops = int(hnsw_node.get("Actual Loops", -1))
            if hnsw_actual_rows < 0 or hnsw_actual_loops < 1:
                failures.append("HNSW scan lacks valid actual row/loop counts")

        expected_mode = "off" if method == "hnsw_standard" else "strict_order"
        expected_settings.update({
            "hnsw.ef_search": "40",
            "hnsw.iterative_scan": expected_mode,
            "hnsw.max_scan_tuples": "20000",
            "hnsw.scan_mem_multiplier": "1",
            "work_mem": "64MB",
            "enable_seqscan": "off",
            "enable_bitmapscan": "off",
        })
    else:
        failures.append(f"unknown method {method}")

    for name, expected in expected_settings.items():
        if observed_settings.get(name) != expected:
            failures.append(
                f"session setting {name} expected {expected}, got {observed_settings.get(name)}"
            )

    actual_rows = int(root.get("Actual Rows", -1))
    actual_loops = int(root.get("Actual Loops", -1))
    if actual_rows < 0 or actual_loops < 1:
        failures.append("plan lacks valid actual row/loop counts")
    if hnsw_actual_rows is not None and hnsw_actual_rows != actual_rows:
        failures.append(
            f"HNSW scan actual rows {hnsw_actual_rows} differ from root actual rows {actual_rows}"
        )
    if fetched_result_count is not None:
        if fetched_result_count < 0:
            failures.append("fetched result count is negative")
        elif actual_loops != 1 or actual_rows != fetched_result_count:
            failures.append(
                f"root actual rows {actual_rows} differ from fetched result count "
                f"{fetched_result_count}"
            )
        if hnsw_actual_rows is not None and (
            hnsw_actual_loops != 1 or hnsw_actual_rows != fetched_result_count
        ):
            failures.append(
                f"HNSW scan actual rows {hnsw_actual_rows} differ from fetched result count "
                f"{fetched_result_count}"
            )
    result = {
        "node_types": node_types,
        "index_names": index_names,
        "relations": relations,
        "hnsw_scan_node_path": hnsw_path,
        "vector_order_evidence": vector_order_evidence,
        "filter_expression": None if hnsw_node is None else hnsw_node.get("Filter"),
        "actual_rows": actual_rows,
        "actual_loops": actual_loops,
        "hnsw_scan_actual_rows": hnsw_actual_rows,
        "hnsw_scan_actual_loops": hnsw_actual_loops,
        "fetched_result_count": fetched_result_count,
        "rows_removed_by_filter": None
        if hnsw_node is None
        else int(hnsw_node.get("Rows Removed by Filter", 0)),
        "observed_session_settings": observed_settings,
        "explain_settings": document[0].get("Settings", {}),
        "passed": not failures,
        "failures": failures,
    }
    return result


def audit_plan(
    connection: psycopg.Connection[Any],
    *,
    method: str,
    threshold: int,
    query_id: int,
    query_vector: np.ndarray,
    k: int,
    scale_rows: int,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    search = search_sql(method, threshold, k)
    if search.count("%s") != 1:
        raise AssertionError("plan audit requires the single-bound-vector search SQL")
    server_search = search.replace("%s", "$1")
    prepared_lookup = (
        "SELECT name, statement, parameter_types::text, generic_plans, custom_plans "
        "FROM pg_prepared_statements WHERE statement = %s "
        "AND cardinality(parameter_types) = 1"
    )
    with connection.cursor() as cursor:
        # This untimed execution creates/reuses exactly the prepared query that the
        # timed workload uses. EXPLAIN of the unprepared template could select a
        # custom plan, even while the benchmark executes a cached generic plan.
        cursor.execute(search, search_parameters(method, query_vector), prepare=True)
        fetched_rows = cursor.fetchall()
        cursor.execute(prepared_lookup, (server_search,), prepare=False)
        prepared = cursor.fetchall()
        if len(prepared) != 1:
            raise AssertionError("expected exactly one matching prepared search statement")
        name, prepared_sql, parameter_types, generic_before, custom_before = prepared[0]
        if generic_before < 1 or custom_before != 0:
            raise AssertionError("search statement did not exclusively use a generic plan")
        vector_text = "[" + ",".join(repr(float(value)) for value in query_vector) + "]"
        statement = sql.SQL(
            "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, TIMING OFF, SUMMARY ON, FORMAT JSON) "
            "EXECUTE {} ({}::vector)"
        ).format(sql.Identifier(name), sql.Literal(vector_text))
        cursor.execute(statement, prepare=False)
        document = cursor.fetchone()[0]
        cursor.execute(prepared_lookup, (server_search,), prepare=False)
        after = cursor.fetchall()
        if (
            len(after) != 1
            or after[0][:3] != prepared[0][:3]
            or after[0][3] != generic_before + 1
            or after[0][4] != 0
        ):
            raise AssertionError("EXPLAIN did not execute the matching prepared generic plan")
    settings = session_settings(connection)
    assertions = verify_plan_document(
        method=method,
        threshold=threshold,
        document=document,
        observed_settings=settings,
        fetched_result_count=len(fetched_rows),
    )
    plan_id = hashlib.sha256(
        f"m2-plan-v1|{scale_rows}|{method}|{threshold}|{query_id}".encode()
    ).hexdigest()[:20]
    record = {
        "schema_version": 1,
        "plan_id": plan_id,
        "scale_rows": scale_rows,
        "method": method,
        "filter_threshold": threshold,
        "query_id": query_id,
        "expected_index": None if method == "exact" else HNSW_INDEX,
        "plan_capture": "EXPLAIN ANALYZE EXECUTE of the workload prepared generic statement",
        "prepared_statement": {
            "name": name,
            "statement": prepared_sql,
            "parameter_types": parameter_types,
            "generic_plans_before_explain": int(generic_before),
            "generic_plans_after_explain": int(after[0][3]),
            "custom_plans_before_explain": int(custom_before),
            "custom_plans_after_explain": int(after[0][4]),
        },
        "fetched_result_ids": [int(row[0]) for row in fetched_rows],
        "fetched_result_distances": [float(row[1]) for row in fetched_rows],
        **assertions,
    }
    return plan_id, document, record
