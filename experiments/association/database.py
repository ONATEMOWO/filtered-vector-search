"""Small mode-aware PostgreSQL adapter; legacy benchmark code is unchanged.

Both metadata assignments are inserted before graph construction. Comparisons
change only the predicate column, never heap rows or the HNSW graph between modes.
"""

from __future__ import annotations

import hashlib
import re
import struct
import time
from datetime import timezone
from typing import Any, Iterable

import numpy as np
from psycopg import sql

from experiments.milestone2.config import canonical_json_bytes
from experiments.milestone2.database import session_settings
from experiments.milestone2.ground_truth import make_ground_truth_record
from experiments.milestone2.plans import walk_plan

SCHEMA = "association"
EXACT_TABLE = f"{SCHEMA}.sift_exact"
HNSW_TABLE = f"{SCHEMA}.sift_hnsw"
HNSW_INDEX = "sift_hnsw_embedding_idx"
MODE_COLUMNS = {"legacy": "filter_bucket", "radial": "radial_bucket"}
METHODS = ("exact", "hnsw_standard", "hnsw_iterative")
FILTERS = (50, 20, 10, 5, 1)
RELATIONS = {
    "sift_exact": "r", "sift_hnsw": "r", "sift_exact_pkey": "i",
    "sift_hnsw_pkey": "i", "sift_exact_filter_bucket_idx": "i",
    "sift_exact_radial_bucket_idx": "i", HNSW_INDEX: "i",
}
BUILD_SETTINGS = {"maintenance_work_mem": "1GB", "max_parallel_maintenance_workers": "0"}


def column_for(mode: str) -> str:
    if mode not in MODE_COLUMNS:
        raise ValueError(f"unknown metadata mode: {mode}")
    return MODE_COLUMNS[mode]


def _search_arguments(mode: str, threshold: int, k: int) -> str:
    column = column_for(mode)
    if type(threshold) is not int or threshold not in FILTERS:
        raise ValueError("threshold is not in the frozen filter matrix")
    if type(k) is not int or k != 10:
        raise ValueError("association experiment requires k=10")
    return column


def search_sql(method: str, mode: str, threshold: int, k: int = 10) -> str:
    column = _search_arguments(mode, threshold, k)
    if method not in METHODS:
        raise ValueError(f"unknown search method: {method}")
    table = EXACT_TABLE if method == "exact" else HNSW_TABLE
    ordering = "distance, id" if method == "exact" else "distance"
    return (f"SELECT id, embedding <-> %s::vector AS distance FROM {table} "
            f"WHERE {column} < {threshold} ORDER BY {ordering} LIMIT {k}")


def ground_truth_sql(mode: str, threshold: int, k: int = 10) -> str:
    column = _search_arguments(mode, threshold, k)
    return (f"SELECT id, embedding <-> %s::vector AS distance FROM {EXACT_TABLE} "
            f"WHERE {column} < {threshold} ORDER BY distance FETCH FIRST {k} ROWS WITH TIES")


def _arrays(base_ids, vectors, legacy, radial) -> tuple[np.ndarray, ...]:
    identifiers, values, old, geometry = map(np.asarray, (base_ids, vectors, legacy, radial))
    n = len(identifiers)
    if n <= 0 or n % 100 or identifiers.shape != (n,) or values.shape != (n, 128):
        raise ValueError("expected a positive multiple of 100 rows and 128-dimensional vectors")
    if not np.issubdtype(identifiers.dtype, np.integer) or np.any(identifiers < 0) or len(np.unique(identifiers)) != n:
        raise ValueError("base IDs must be unique nonnegative integers")
    if not np.isfinite(values).all() or values.dtype != np.float32:
        raise ValueError("source vectors must be finite float32 values")
    for buckets in (old, geometry):
        if buckets.shape != (n,) or not np.issubdtype(buckets.dtype, np.integer):
            raise ValueError("metadata must be aligned integer arrays")
        if np.any(buckets < 0) or np.any(buckets >= 100) or not np.all(np.bincount(buckets, minlength=100) == n // 100):
            raise ValueError("every metadata bucket must have exactly scale_rows/100 rows")
    if not np.array_equal(old, np.arange(n) % 100):
        raise ValueError("legacy assignment must remain scale_rank modulo 100")
    return identifiers, values, old, geometry


def source_stream_checksum(base_ids, vectors, legacy, radial) -> str:
    """Hash row identity, both labels and network-order pgvector binary payload."""
    digest = hashlib.sha256()
    for rank, (identifier, vector, old, geometry) in enumerate(zip(base_ids, vectors, legacy, radial, strict=True)):
        digest.update(struct.pack("<iihh", int(identifier), rank, int(old), int(geometry)))
        digest.update(struct.pack(">HH", len(vector), 0))
        digest.update(np.asarray(vector, dtype=">f4").tobytes())
    return digest.hexdigest()


def _table_stream_checksum(connection, table: str) -> str:
    if table not in (EXACT_TABLE, HNSW_TABLE):
        raise ValueError("unknown checksum table")
    digest = hashlib.sha256()
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id, scale_rank, filter_bucket, radial_bucket, vector_send(embedding) "
                       f"FROM {table} ORDER BY scale_rank", prepare=False)
        while rows := cursor.fetchmany(2000):
            for identifier, rank, old, geometry, vector_bytes in rows:
                digest.update(struct.pack("<iihh", identifier, rank, old, geometry))
                digest.update(bytes(vector_bytes))
    return digest.hexdigest()


def load_scale(connection, *, base_ids, vectors, legacy, radial) -> dict[str, Any]:
    identifiers, values, old, geometry = _arrays(base_ids, vectors, legacy, radial)
    phases = {}
    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}", prepare=False)
        cursor.execute(f"DROP TABLE IF EXISTS {HNSW_TABLE}", prepare=False)
        cursor.execute(f"DROP TABLE IF EXISTS {EXACT_TABLE}", prepare=False)
        for table in (EXACT_TABLE, HNSW_TABLE):
            cursor.execute(f"CREATE TABLE {table} ("
                           "id integer PRIMARY KEY CHECK (id >= 0), "
                           "scale_rank integer NOT NULL CHECK (scale_rank >= 0), "
                           "filter_bucket smallint NOT NULL CHECK (filter_bucket BETWEEN 0 AND 99), "
                           "radial_bucket smallint NOT NULL CHECK (radial_bucket BETWEEN 0 AND 99), "
                           "embedding vector(128) NOT NULL)", prepare=False)
        with cursor.copy(f"COPY {EXACT_TABLE} (id, scale_rank, filter_bucket, radial_bucket, embedding) FROM STDIN") as copy:
            for rank in range(len(identifiers)):
                copy.write_row((int(identifiers[rank]), rank, int(old[rank]), int(geometry[rank]), values[rank]))
    phases["schema_and_copy_exact_ns"] = time.perf_counter_ns() - started
    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        cursor.execute(f"INSERT INTO {HNSW_TABLE} (id, scale_rank, filter_bucket, radial_bucket, embedding) "
                       f"SELECT id, scale_rank, filter_bucket, radial_bucket, embedding FROM {EXACT_TABLE} "
                       "ORDER BY scale_rank", prepare=False)
    phases["copy_hnsw_from_exact_ns"] = time.perf_counter_ns() - started
    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        for column in MODE_COLUMNS.values():
            cursor.execute(f"CREATE INDEX sift_exact_{column}_idx ON {EXACT_TABLE} USING btree ({column})", prepare=False)
        for name, value in BUILD_SETTINGS.items():
            cursor.execute("SELECT set_config(%s, %s, false)", (name, value), prepare=False)
        cursor.execute("SELECT current_setting('maintenance_work_mem'), current_setting('max_parallel_maintenance_workers')", prepare=False)
        observed = cursor.fetchone()
        if tuple(observed) != tuple(BUILD_SETTINGS.values()):
            raise AssertionError(f"HNSW build settings differ: {observed}")
    phases["exact_index_ns"] = time.perf_counter_ns() - started
    phases["hnsw_build_settings"] = {**BUILD_SETTINGS, "m": 16, "ef_construction": 64}
    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE INDEX {HNSW_INDEX} ON {HNSW_TABLE} USING hnsw (embedding vector_l2_ops) "
                       "WITH (m = 16, ef_construction = 64)", prepare=False)
    phases["hnsw_build_ns"] = time.perf_counter_ns() - started
    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        for table in (EXACT_TABLE, HNSW_TABLE):
            for column in MODE_COLUMNS.values():
                cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET STATISTICS 1000", prepare=False)
            cursor.execute(f"VACUUM (ANALYZE, FREEZE) {table}", prepare=False)
        cursor.execute("CHECKPOINT", prepare=False)
    phases["vacuum_analyze_checkpoint_ns"] = time.perf_counter_ns() - started
    return phases


def identity(connection) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_postmaster_start_time(), (pg_control_system()).system_identifier::text, "
                       "current_database(), current_setting('server_version_num')", prepare=False)
        started, system, database, version = cursor.fetchone()
        cursor.execute("SELECT c.relname, c.oid::bigint, pg_relation_filenode(c.oid)::bigint, c.relkind "
                       "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                       "WHERE n.nspname=%s AND c.relkind IN ('r','i') ORDER BY c.relname", (SCHEMA,), prepare=False)
        relations = [{"relation": name, "oid": int(oid), "filenode": int(filenode), "kind": kind}
                     for name, oid, filenode, kind in cursor.fetchall()]
    if (len(relations) != 7 or {r["relation"]: r["kind"] for r in relations} != RELATIONS
            or any(r["oid"] <= 0 or r["filenode"] <= 0 for r in relations)
            or any(len({r[field] for r in relations}) != 7 for field in ("oid", "filenode"))):
        raise AssertionError("association identity does not contain seven distinct physical relations")
    return {"schema": SCHEMA, "postmaster_started_at": started.astimezone(timezone.utc).isoformat(),
            "system_identifier": str(system), "database": str(database), "server_version_num": str(version),
            "relations": relations}


def evidence(connection, *, base_ids, vectors, legacy, radial) -> dict[str, Any]:
    identifiers, values, old, geometry = _arrays(base_ids, vectors, legacy, radial)
    n = len(identifiers)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT (SELECT count(*) FROM {EXACT_TABLE}), (SELECT count(*) FROM {HNSW_TABLE}), "
                       f"(SELECT count(*) FROM {EXACT_TABLE} e FULL JOIN {HNSW_TABLE} h USING (id) "
                       "WHERE e.id IS NULL OR h.id IS NULL OR e.scale_rank IS DISTINCT FROM h.scale_rank "
                       "OR e.filter_bucket IS DISTINCT FROM h.filter_bucket OR e.radial_bucket IS DISTINCT FROM h.radial_bucket "
                       "OR e.embedding::text IS DISTINCT FROM h.embedding::text), "
                       f"(SELECT min(vector_dims(embedding)) FROM {EXACT_TABLE}), "
                       f"(SELECT max(vector_dims(embedding)) FROM {EXACT_TABLE}), "
                       f"(SELECT count(*) FROM {EXACT_TABLE} WHERE embedding::text ~* '(nan|infinity)'), "
                       f"(SELECT count(*) FROM {HNSW_TABLE} WHERE embedding::text ~* '(nan|infinity)')", prepare=False)
        observed = tuple(cursor.fetchone())
        if observed != (n, n, 0, 128, 128, 0, 0):
            raise AssertionError(f"physical table equivalence/vector validation failed: {observed}")
        cursor.execute(f"SELECT count(DISTINCT scale_rank), min(scale_rank), max(scale_rank), "
                       f"count(*) FILTER (WHERE filter_bucket <> scale_rank % 100) FROM {EXACT_TABLE}", prepare=False)
        ranks = tuple(cursor.fetchone())
        if ranks != (n, 0, n - 1, 0):
            raise AssertionError("scale rank or legacy metadata contract differs")
        filter_counts = {}
        for mode, column in MODE_COLUMNS.items():
            counts = {}
            for threshold in FILTERS:
                cursor.execute(f"SELECT (SELECT count(*) FROM {EXACT_TABLE} WHERE {column} < %s), "
                               f"(SELECT count(*) FROM {HNSW_TABLE} WHERE {column} < %s)",
                               (threshold, threshold), prepare=False)
                exact_count, ann_count = cursor.fetchone()
                expected = n * threshold // 100
                if (exact_count, ann_count) != (expected, expected):
                    raise AssertionError(f"metadata count differs: {mode}/{threshold}")
                counts[str(threshold)] = {"exact": exact_count, "hnsw": ann_count, "expected": expected}
            filter_counts[mode] = counts
        cursor.execute("SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes "
                       "WHERE schemaname=%s ORDER BY tablename,indexname", (SCHEMA,), prepare=False)
        indexes = [{"schema": s, "table": t, "index": i, "definition": d} for s, t, i, d in cursor.fetchall()]
        expected_indexes = {name for name, kind in RELATIONS.items() if kind == "i"}
        if len(indexes) != 5 or {r["index"] for r in indexes} != expected_indexes:
            raise AssertionError("index matrix differs from the two metadata B-trees and one graph contract")
        for mode, column in MODE_COLUMNS.items():
            matches = [r for r in indexes if r["index"] == f"sift_exact_{column}_idx"]
            if len(matches) != 1 or matches[0]["table"] != "sift_exact" or f"USING btree ({column})" not in matches[0]["definition"]:
                raise AssertionError(f"exact metadata B-tree differs: {mode}")
        graph = [r for r in indexes if r["index"] == HNSW_INDEX]
        if len(graph) != 1 or graph[0]["table"] != "sift_hnsw" or not all(
            fragment in graph[0]["definition"] for fragment in ("USING hnsw (embedding vector_l2_ops)", "m='16'", "ef_construction='64'")
        ):
            raise AssertionError("HNSW graph definition differs")
        cursor.execute("SELECT tablename, attname, null_frac, n_distinct, most_common_vals::text, most_common_freqs::text "
                       "FROM pg_stats WHERE schemaname=%s AND attname IN ('filter_bucket','radial_bucket') "
                       "ORDER BY tablename,attname", (SCHEMA,), prepare=False)
        statistics = [{"table": t, "column": c, "null_fraction": z, "distinct": d,
                       "most_common_values": v, "most_common_frequencies": f} for t, c, z, d, v, f in cursor.fetchall()]
        if len(statistics) != 4 or any(r["null_fraction"] != 0 or r["distinct"] != 100 for r in statistics):
            raise AssertionError("metadata statistics are incomplete or differ")
        cursor.execute("SELECT c.relname,c.relkind,pg_relation_size(c.oid),pg_total_relation_size(c.oid) "
                       "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                       "WHERE n.nspname=%s AND c.relkind IN ('r','i') ORDER BY c.relname", (SCHEMA,), prepare=False)
        sizes = [{"relation": r, "kind": k, "relation_bytes": b, "total_bytes": t} for r, k, b, t in cursor.fetchall()]
    expected_digest = source_stream_checksum(identifiers, values, old, geometry)
    exact_digest, ann_digest = (_table_stream_checksum(connection, table) for table in (EXACT_TABLE, HNSW_TABLE))
    if exact_digest != expected_digest or ann_digest != expected_digest:
        raise AssertionError("full ordered table vectors/IDs/metadata differ from canonical source")
    if len(sizes) != 7 or {r["relation"]: r["kind"] for r in sizes} != RELATIONS or any(r["relation_bytes"] <= 0 for r in sizes):
        raise AssertionError("relation size matrix differs")
    return {"scale_rows": n, "exact_count": n, "hnsw_count": n, "unequal_row_count": 0,
            "dimensions": {"minimum": 128, "maximum": 128}, "nonfinite_vector_counts": {"exact": 0, "hnsw": 0},
            "rank_contract": {"distinct_ranks": n, "minimum": 0, "maximum": n - 1, "legacy_bucket_mismatches": 0},
            "filter_counts": filter_counts, "source_vector_stream_sha256": expected_digest,
            "exact_vector_stream_sha256": exact_digest, "hnsw_vector_stream_sha256": ann_digest,
            "all_source_rows_and_both_metadata_equal": True, "indexes": indexes, "statistics": statistics,
            "relation_sizes": sizes, "identity": identity(connection)}


def make_truth_record(*, mode: str, metadata_sha256: str, **arguments) -> dict[str, Any]:
    column_for(mode)
    record = make_ground_truth_record(scale_manifest_sha256=metadata_sha256, **arguments)
    record.update(metadata_mode=mode, metadata_sha256=metadata_sha256,
                  generation_method=f"PostgreSQL exact filtered L2 search on {EXACT_TABLE} with no vector index",
                  generation_sql=ground_truth_sql(mode, arguments["threshold"], arguments["k"]))
    record.pop("record_sha256")
    record["record_sha256"] = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return record


def generate_truth(connection, *, mode: str, run_id: str, scale_rows: int, thresholds: Iterable[int],
                   query_ids: Iterable[int], query_vectors: dict, dataset_sha256: str,
                   metadata_sha256: str) -> tuple[list[dict[str, Any]], int]:
    column_for(mode)
    filters = tuple(thresholds)
    started = time.perf_counter_ns()
    records = []
    with connection.cursor() as cursor:
        for query in query_ids:
            for threshold in filters:
                cursor.execute(ground_truth_sql(mode, threshold), (query_vectors[query],), prepare=True)
                records.append(make_truth_record(
                    mode=mode, metadata_sha256=metadata_sha256, run_id=run_id, scale_rows=scale_rows,
                    threshold=threshold, qualifying_count=scale_rows * threshold // 100, query_id=query,
                    k=10, rows=cursor.fetchall(), dataset_sha256=dataset_sha256))
    return records, time.perf_counter_ns() - started


def verify_plan_document(*, method: str, mode: str, threshold: int, document: list,
                         observed_settings: dict, fetched_result_count: int | None = None) -> dict[str, Any]:
    column = _search_arguments(mode, threshold, 10)
    if method not in METHODS or not document or "Plan" not in document[0]:
        raise AssertionError("unknown method or missing plan")
    root = document[0]["Plan"]
    paths = list(walk_plan(root))
    nodes = [n for _, n in paths]
    failures = []
    table = "sift_exact" if method == "exact" else "sift_hnsw"
    relations = [n for n in nodes if "Relation Name" in n]
    if not relations or any(n.get("Relation Name") != table or n.get("Schema") != SCHEMA for n in relations):
        failures.append("plan reads the wrong table or schema")
    predicates = [str(n.get(key, "")) for n in nodes for key in ("Filter", "Index Cond", "Recheck Cond")]
    pattern = rf"\b{column}\s*<\s*{threshold}(?!\d)"
    if not any(re.search(pattern, p) for p in predicates):
        failures.append("plan lacks the required mode-specific predicate")
    other_column = next(c for c in MODE_COLUMNS.values() if c != column)
    if any(re.search(rf"\b{other_column}\b", p) for p in predicates):
        failures.append("plan contains the other metadata mode predicate")
    order_texts = [str(n.get(key, "")) for n in nodes for key in ("Order By", "Sort Key")]
    if not any("embedding" in value and "<->" in value and "$1" in value for value in order_texts):
        failures.append("plan lacks ordering by the single generic vector parameter")
    expected_settings = {"jit": "off", "plan_cache_mode": "force_generic_plan", "statement_timeout": "2min"}
    ann_path, ann = None, None
    if root.get("Node Type") != "Limit":
        failures.append("search plan root is not Limit")
    if method == "exact":
        expected_settings.update({name: "on" for name in ("enable_seqscan", "enable_bitmapscan", "enable_indexscan", "enable_indexonlyscan")})
        if any("hnsw" in str(n.get("Index Name", "")) for n in nodes):
            failures.append("exact plan uses HNSW")
        allowed = {"sift_exact_pkey", "sift_exact_filter_bucket_idx", "sift_exact_radial_bucket_idx"}
        if any(n["Index Name"] not in allowed for n in nodes if "Index Name" in n):
            failures.append("exact plan uses an unexpected index")
    else:
        expected_settings.update({"hnsw.ef_search": "40", "hnsw.iterative_scan": "off" if method == "hnsw_standard" else "strict_order",
                                  "hnsw.max_scan_tuples": "20000", "hnsw.scan_mem_multiplier": "1", "work_mem": "64MB",
                                  "enable_seqscan": "off", "enable_bitmapscan": "off"})
        if len(nodes) != 2 or nodes[1].get("Node Type") != "Index Scan" or nodes[1].get("Index Name") != HNSW_INDEX:
            failures.append("HNSW path must be exactly Limit over its Index Scan, without sort or alternate scans")
        else:
            ann_path, ann = paths[1]
            order = str(ann.get("Order By", ""))
            if not all(part in order for part in ("embedding", "<->", "$1")):
                failures.append("HNSW scan does not order by the generic vector parameter")
            if not re.search(pattern, str(ann.get("Filter", ""))):
                failures.append("metadata predicate is not post-filtered on the HNSW scan")
    for name, expected in expected_settings.items():
        if observed_settings.get(name) != expected:
            failures.append(f"setting {name}: expected {expected}, got {observed_settings.get(name)}")
    count, loops = root.get("Actual Rows", -1), root.get("Actual Loops", -1)
    if type(count) not in (int, float) or not 0 <= count <= 10 or loops != 1:
        failures.append("root actual row/loop counts are invalid")
    if ann is not None and (ann.get("Actual Rows") != count or ann.get("Actual Loops") != 1):
        failures.append("HNSW scan and root actual row/loop counts differ")
    if fetched_result_count is not None and (type(fetched_result_count) is not int or not 0 <= fetched_result_count <= 10 or fetched_result_count != count):
        failures.append("fetched result count differs from plan")
    if method == "exact" and count != 10:
        failures.append("exact plan returned fewer than k")
    return {"passed": not failures, "failures": failures, "metadata_mode": mode,
            "node_types": [n.get("Node Type") for n in nodes], "index_names": [n["Index Name"] for n in nodes if "Index Name" in n],
            "relations": [n["Relation Name"] for n in relations], "schemas": [n.get("Schema") for n in relations],
            "actual_rows": count, "actual_loops": loops, "fetched_result_count": fetched_result_count,
            "hnsw_scan_node_path": ann_path, "filter_expression": None if ann is None else ann.get("Filter"),
            "hnsw_scan_actual_rows": None if ann is None else ann.get("Actual Rows"),
            "hnsw_scan_actual_loops": None if ann is None else ann.get("Actual Loops"),
            "rows_removed_by_filter": None if ann is None else ann.get("Rows Removed by Filter", 0),
            "observed_session_settings": observed_settings, "explain_settings": document[0].get("Settings", {})}


def audit_plan(connection, *, method: str, mode: str, threshold: int, query_id: int,
               query_vector: np.ndarray, scale_rows: int) -> tuple[str, list, dict]:
    search = search_sql(method, mode, threshold)
    if search.count("%s") != 1:
        raise AssertionError("search SQL must bind one vector")
    server_sql = search.replace("%s", "$1")
    lookup = ("SELECT name, statement, parameter_types::text, generic_plans, custom_plans "
              "FROM pg_prepared_statements WHERE statement=%s AND cardinality(parameter_types)=1")
    with connection.cursor() as cursor:
        cursor.execute(search, (query_vector,), prepare=True)
        fetched = cursor.fetchall()
        cursor.execute(lookup, (server_sql,), prepare=False)
        found = cursor.fetchall()
        if len(found) != 1 or found[0][2] != "{vector}" or found[0][3] < 1 or found[0][4] != 0:
            raise AssertionError("expected one generic prepared vector statement")
        name, statement, parameter_types, generic_before, custom_before = found[0]
        vector_text = "[" + ",".join(repr(float(v)) for v in query_vector) + "]"
        explain = sql.SQL("EXPLAIN (ANALYZE, BUFFERS, SETTINGS, VERBOSE, TIMING OFF, SUMMARY ON, FORMAT JSON) EXECUTE {} ({}::vector)").format(
            sql.Identifier(name), sql.Literal(vector_text))
        cursor.execute(explain, prepare=False)
        document = cursor.fetchone()[0]
        cursor.execute(lookup, (server_sql,), prepare=False)
        after = cursor.fetchall()
        if len(after) != 1 or after[0][:3] != found[0][:3] or after[0][3] != generic_before + 1 or after[0][4] != 0:
            raise AssertionError("EXPLAIN did not execute the same prepared generic statement")
    settings = session_settings(connection)
    assertions = verify_plan_document(method=method, mode=mode, threshold=threshold, document=document,
                                      observed_settings=settings, fetched_result_count=len(fetched))
    plan_id = hashlib.sha256(f"association-plan-v1|{scale_rows}|{method}|{mode}|{threshold}|{query_id}".encode()).hexdigest()[:20]
    record = {"schema_version": 1, "plan_id": plan_id, "scale_rows": scale_rows, "method": method,
              "metadata_mode": mode, "filter_threshold": threshold, "query_id": query_id,
              "expected_index": None if method == "exact" else HNSW_INDEX,
              "plan_capture": "EXPLAIN ANALYZE VERBOSE EXECUTE of the workload prepared generic statement",
              "prepared_statement": {"name": name, "statement": statement, "parameter_types": parameter_types,
                                     "generic_plans_before_explain": int(generic_before), "generic_plans_after_explain": int(after[0][3]),
                                     "custom_plans_before_explain": int(custom_before), "custom_plans_after_explain": int(after[0][4])},
              "fetched_result_ids": [int(r[0]) for r in fetched], "fetched_result_distances": [float(r[1]) for r in fetched],
              **assertions}
    return plan_id, document, record
