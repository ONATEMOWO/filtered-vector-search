"""Untimed EXPLAIN capture and strict method-routing assertions."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any

import numpy as np
import psycopg

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
    if method == "exact":
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
            if hnsw_node.get("Node Type") not in {"Index Scan", "Index Only Scan"}:
                failures.append("HNSW access is not an index scan")
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

        expected_mode = "off" if method == "hnsw_standard" else "strict_order"
        expected_settings = {
            "hnsw.ef_search": "40",
            "hnsw.iterative_scan": expected_mode,
            "hnsw.max_scan_tuples": "20000",
            "hnsw.scan_mem_multiplier": "1",
            "work_mem": "64MB",
            "enable_seqscan": "off",
            "enable_bitmapscan": "off",
        }
        for name, expected in expected_settings.items():
            if observed_settings.get(name) != expected:
                failures.append(
                    f"session setting {name} expected {expected}, got {observed_settings.get(name)}"
                )
    else:
        failures.append(f"unknown method {method}")

    actual_rows = int(root.get("Actual Rows", -1))
    actual_loops = int(root.get("Actual Loops", -1))
    if actual_rows < 0 or actual_loops < 1:
        failures.append("plan lacks valid actual row/loop counts")
    result = {
        "node_types": node_types,
        "index_names": index_names,
        "relations": relations,
        "hnsw_scan_node_path": hnsw_path,
        "vector_order_evidence": vector_order_evidence,
        "filter_expression": None if hnsw_node is None else hnsw_node.get("Filter"),
        "actual_rows": actual_rows,
        "actual_loops": actual_loops,
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
    statement = (
        "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, TIMING OFF, SUMMARY ON, FORMAT JSON) "
        + search
    )
    with connection.cursor() as cursor:
        cursor.execute(statement, search_parameters(method, query_vector), prepare=False)
        document = cursor.fetchone()[0]
    settings = session_settings(connection)
    assertions = verify_plan_document(
        method=method,
        threshold=threshold,
        document=document,
        observed_settings=settings,
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
        **assertions,
    }
    return plan_id, document, record
