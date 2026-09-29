"""Persistent PostgreSQL access, physical scale loading, and timed execution."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import resource
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import psycopg
import psutil
from pgvector.psycopg import register_vector


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "milestone2"
EXACT_TABLE = f"{SCHEMA}.sift_exact"
HNSW_TABLE = f"{SCHEMA}.sift_hnsw"
HNSW_INDEX = "sift_hnsw_embedding_idx"


def connection_parameters() -> dict[str, Any]:
    return {
        "host": os.environ.get("PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("PGPORT", "55432")),
        "user": os.environ.get("PGUSER", os.environ.get("USER", "postgres")),
        "dbname": os.environ.get("PGDATABASE", "filtered_vector_search"),
        "connect_timeout": 10,
    }


def connect(*, application_name: str, autocommit: bool = True) -> psycopg.Connection[Any]:
    connection = psycopg.connect(
        **connection_parameters(), application_name=application_name, autocommit=autocommit
    )
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(connection)
    return connection


def execute_sql_file(connection: psycopg.Connection[Any], path: Path) -> None:
    statement = path.read_text(encoding="utf-8")
    with connection.cursor() as cursor:
        cursor.execute(statement, prepare=False)


def verify_versions(connection: psycopg.Connection[Any]) -> dict[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('server_version'), current_setting('server_version_num'), "
            "(SELECT extversion FROM pg_extension WHERE extname = 'vector')"
        )
        server, server_number, extension = cursor.fetchone()
    return {
        "postgresql_version": str(server).split()[0],
        "postgresql_version_raw": str(server),
        "postgresql_version_num": str(server_number),
        "pgvector_version": str(extension),
    }


def vector_stream_checksum(connection: psycopg.Connection[Any], table: str) -> str:
    digest = hashlib.sha256()
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, scale_rank, filter_bucket, vector_send(embedding) "
            f"FROM {table} ORDER BY scale_rank",
            prepare=False,
        )
        while True:
            rows = cursor.fetchmany(2_000)
            if not rows:
                break
            for identifier, scale_rank, bucket, vector_bytes in rows:
                digest.update(struct.pack("<iih", identifier, scale_rank, bucket))
                digest.update(bytes(vector_bytes))
    return digest.hexdigest()


def source_stream_checksum(base_ids: np.ndarray, vectors: np.ndarray, buckets: np.ndarray) -> str:
    """Match vector_send's network-order float32 payload using the original source rows."""
    digest = hashlib.sha256()
    for rank, (identifier, vector, bucket) in enumerate(zip(base_ids, vectors, buckets, strict=True)):
        digest.update(struct.pack("<iih", int(identifier), rank, int(bucket)))
        digest.update(struct.pack(">HH", len(vector), 0))
        digest.update(np.asarray(vector, dtype=">f4").tobytes())
    return digest.hexdigest()


def load_scale(
    connection: psycopg.Connection[Any],
    *,
    base_ids: np.ndarray,
    vectors: np.ndarray,
    buckets: np.ndarray,
    hnsw_build_settings: Mapping[str, Any],
) -> dict[str, Any]:
    if len(base_ids) != len(vectors) or len(base_ids) != len(buckets):
        raise ValueError("scale arrays have different lengths")
    timings: dict[str, Any] = {}
    execute_sql_file(connection, ROOT / "sql" / "milestone2" / "001_schema.sql")

    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        with cursor.copy(
            f"COPY {EXACT_TABLE} (id, scale_rank, filter_bucket, embedding) FROM STDIN"
        ) as copy:
            for rank in range(len(base_ids)):
                copy.write_row(
                    (
                        int(base_ids[rank]),
                        rank,
                        int(buckets[rank]),
                        vectors[rank],
                    )
                )
    timings["copy_exact_ns"] = time.perf_counter_ns() - started

    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {HNSW_TABLE} (id, scale_rank, filter_bucket, embedding) "
            f"SELECT id, scale_rank, filter_bucket, embedding FROM {EXACT_TABLE} "
            "ORDER BY scale_rank",
            prepare=False,
        )
    timings["copy_hnsw_from_exact_ns"] = time.perf_counter_ns() - started

    started = time.perf_counter_ns()
    execute_sql_file(connection, ROOT / "sql" / "milestone2" / "002_exact_indexes.sql")
    timings["exact_index_ns"] = time.perf_counter_ns() - started

    with connection.cursor() as cursor:
        maintenance_work_mem = str(hnsw_build_settings["build_maintenance_work_mem"])
        max_parallel_workers = str(
            int(hnsw_build_settings["build_max_parallel_maintenance_workers"])
        )
        cursor.execute(
            "SELECT set_config('maintenance_work_mem', %s, false)",
            (maintenance_work_mem,),
            prepare=False,
        )
        cursor.execute(
            "SELECT set_config('max_parallel_maintenance_workers', %s, false)",
            (max_parallel_workers,),
            prepare=False,
        )
        cursor.execute(
            "SELECT current_setting('maintenance_work_mem'), "
            "current_setting('max_parallel_maintenance_workers')",
            prepare=False,
        )
        observed_build_settings = cursor.fetchone()
        if observed_build_settings != (maintenance_work_mem, max_parallel_workers):
            raise AssertionError(
                "HNSW build settings differ from the frozen protocol: "
                f"{observed_build_settings!r}"
            )
    timings["hnsw_build_settings"] = {
        "maintenance_work_mem": observed_build_settings[0],
        "max_parallel_maintenance_workers": observed_build_settings[1],
    }
    started = time.perf_counter_ns()
    execute_sql_file(connection, ROOT / "sql" / "milestone2" / "003_hnsw_index.sql")
    timings["hnsw_build_ns"] = time.perf_counter_ns() - started

    started = time.perf_counter_ns()
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {EXACT_TABLE} ALTER COLUMN filter_bucket SET STATISTICS 1000")
        cursor.execute(f"ALTER TABLE {HNSW_TABLE} ALTER COLUMN filter_bucket SET STATISTICS 1000")
        cursor.execute(f"VACUUM (ANALYZE, FREEZE) {EXACT_TABLE}", prepare=False)
        cursor.execute(f"VACUUM (ANALYZE, FREEZE) {HNSW_TABLE}", prepare=False)
        cursor.execute("CHECKPOINT", prepare=False)
    timings["vacuum_analyze_checkpoint_ns"] = time.perf_counter_ns() - started
    return timings


def database_evidence(
    connection: psycopg.Connection[Any], *, scale_rows: int, thresholds: Iterable[int]
) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
SELECT
  (SELECT count(*) FROM {EXACT_TABLE}),
  (SELECT count(*) FROM {HNSW_TABLE}),
  (SELECT count(*)
   FROM {EXACT_TABLE} e
   FULL JOIN {HNSW_TABLE} h USING (id)
   WHERE e.id IS NULL OR h.id IS NULL
      OR e.scale_rank IS DISTINCT FROM h.scale_rank
      OR e.filter_bucket IS DISTINCT FROM h.filter_bucket
      OR e.embedding::text IS DISTINCT FROM h.embedding::text),
  (SELECT min(vector_dims(embedding)) FROM {EXACT_TABLE}),
  (SELECT max(vector_dims(embedding)) FROM {EXACT_TABLE}),
  (SELECT count(*) FROM {EXACT_TABLE}
   WHERE embedding::text ~* '(nan|infinity)'),
  (SELECT count(*) FROM {HNSW_TABLE}
   WHERE embedding::text ~* '(nan|infinity)');
""",
            prepare=False,
        )
        (
            exact_count,
            hnsw_count,
            unequal,
            min_dims,
            max_dims,
            exact_nonfinite,
            hnsw_nonfinite,
        ) = cursor.fetchone()
        if (
            exact_count,
            hnsw_count,
            unequal,
            min_dims,
            max_dims,
            exact_nonfinite,
            hnsw_nonfinite,
        ) != (
            scale_rows,
            scale_rows,
            0,
            128,
            128,
            0,
            0,
        ):
            raise AssertionError(
                "table equivalence/dimension/non-finite check failed: "
                f"{(exact_count, hnsw_count, unequal, min_dims, max_dims, exact_nonfinite, hnsw_nonfinite)}"
            )

        filter_counts: dict[str, dict[str, int]] = {}
        cursor.execute(
            f"SELECT count(DISTINCT scale_rank), min(scale_rank), max(scale_rank), "
            f"count(*) FILTER (WHERE filter_bucket <> scale_rank % 100) FROM {EXACT_TABLE}",
            prepare=False,
        )
        rank_evidence = cursor.fetchone()
        if rank_evidence != (scale_rows, 0, scale_rows - 1, 0):
            raise AssertionError(f"scale rank/bucket contract failed: {rank_evidence}")
        for threshold in thresholds:
            cursor.execute(
                f"SELECT "
                f"(SELECT count(*) FROM {EXACT_TABLE} WHERE filter_bucket < %s), "
                f"(SELECT count(*) FROM {HNSW_TABLE} WHERE filter_bucket < %s)",
                (threshold, threshold),
            )
            exact_filtered, hnsw_filtered = cursor.fetchone()
            expected = scale_rows * int(threshold) // 100
            if exact_filtered != expected or hnsw_filtered != expected:
                raise AssertionError(
                    f"filter {threshold}: expected {expected}, got {exact_filtered}/{hnsw_filtered}"
                )
            filter_counts[str(threshold)] = {
                "expected": expected,
                "exact": exact_filtered,
                "hnsw": hnsw_filtered,
            }

        cursor.execute(
            "SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = %s ORDER BY tablename, indexname",
            (SCHEMA,),
        )
        indexes = [
            {
                "schema": row[0],
                "table": row[1],
                "index": row[2],
                "definition": row[3],
            }
            for row in cursor.fetchall()
        ]
        exact_vector_indexes = [
            row
            for row in indexes
            if row["table"] == "sift_exact" and "(embedding" in row["definition"]
        ]
        hnsw_filter_indexes = [
            row
            for row in indexes
            if row["table"] == "sift_hnsw" and "(filter_bucket)" in row["definition"]
        ]
        if exact_vector_indexes or hnsw_filter_indexes:
            raise AssertionError("exact/HNSW index separation is invalid")
        exact_filter_indexes = [
            row
            for row in indexes
            if row["table"] == "sift_exact"
            and row["index"] == "sift_exact_filter_bucket_idx"
            and "USING btree (filter_bucket)" in row["definition"]
        ]
        hnsw_vector_indexes = [
            row
            for row in indexes
            if row["table"] == "sift_hnsw"
            and row["index"] == HNSW_INDEX
            and "USING hnsw (embedding vector_l2_ops)" in row["definition"]
            and "m='16'" in row["definition"]
            and "ef_construction='64'" in row["definition"]
        ]
        if len(exact_filter_indexes) != 1 or len(hnsw_vector_indexes) != 1:
            raise AssertionError("required exact metadata/HNSW index definitions are missing")

        cursor.execute(
            "SELECT tablename, attname, null_frac, n_distinct, most_common_vals::text, "
            "most_common_freqs::text FROM pg_stats "
            "WHERE schemaname=%s AND attname='filter_bucket' ORDER BY tablename",
            (SCHEMA,),
        )
        statistics = [
            {
                "table": row[0],
                "column": row[1],
                "null_fraction": row[2],
                "distinct": row[3],
                "most_common_values": row[4],
                "most_common_frequencies": row[5],
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
SELECT c.relname, c.relkind, pg_relation_size(c.oid), pg_total_relation_size(c.oid)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=%s ORDER BY c.relname
""",
            (SCHEMA,),
        )
        relation_sizes = [
            {
                "relation": row[0],
                "kind": row[1],
                "relation_bytes": row[2],
                "total_bytes": row[3],
            }
            for row in cursor.fetchall()
        ]

    exact_checksum = vector_stream_checksum(connection, EXACT_TABLE)
    hnsw_checksum = vector_stream_checksum(connection, HNSW_TABLE)
    if exact_checksum != hnsw_checksum:
        raise AssertionError("ordered exact/HNSW table checksums differ")
    return {
        "scale_rows": scale_rows,
        "exact_count": exact_count,
        "hnsw_count": hnsw_count,
        "unequal_row_count": unequal,
        "rank_contract": {
            "distinct_ranks": rank_evidence[0], "minimum": rank_evidence[1],
            "maximum": rank_evidence[2], "bucket_mismatches": rank_evidence[3],
        },
        "dimensions": {"minimum": min_dims, "maximum": max_dims},
        "nonfinite_vector_counts": {
            "exact": exact_nonfinite,
            "hnsw": hnsw_nonfinite,
            "validation": "case-insensitive vector text scan for NaN or Infinity",
        },
        "filter_counts": filter_counts,
        "indexes": indexes,
        "index_contract": {
            "exact_metadata_btree_present": True,
            "exact_embedding_index_absent": True,
            "hnsw_metadata_btree_absent": True,
            "hnsw_vector_index_present": True,
            "hnsw_operator_class": "vector_l2_ops",
            "hnsw_m": 16,
            "hnsw_ef_construction": 64,
        },
        "statistics": statistics,
        "relation_sizes": relation_sizes,
        "ordered_vector_stream_sha256": exact_checksum,
    }


def validate_source_samples(
    connection: psycopg.Connection[Any],
    *,
    base_ids: np.ndarray,
    vectors: np.ndarray,
    sample_count: int = 100,
) -> dict[str, Any]:
    positions = np.linspace(0, len(base_ids) - 1, min(sample_count, len(base_ids)), dtype=int)
    expected = {int(base_ids[pos]): vectors[pos] for pos in positions}
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, embedding FROM {EXACT_TABLE} WHERE id = ANY(%s) ORDER BY id",
            (list(expected),),
        )
        observed = {int(identifier): np.asarray(vector, dtype=np.float32) for identifier, vector in cursor}
    if set(observed) != set(expected):
        raise AssertionError("database source-vector sample IDs differ")
    for identifier, expected_vector in expected.items():
        if not np.array_equal(observed[identifier], expected_vector):
            raise AssertionError(f"database vector changed for base ID {identifier}")
    return {
        "sample_count": len(expected),
        "ids": sorted(expected),
        "float32_exact_equality": True,
        "normalization_applied": False,
    }


COMMON_SESSION_SETTINGS = (
    "SET jit = off",
    "SET statement_timeout = '120s'",
    "SET plan_cache_mode = force_generic_plan",
)


METHOD_SESSION_SETTINGS = {
    "exact": (),
    "hnsw_standard": (
        "SET work_mem = '64MB'",
        "SET enable_seqscan = off",
        "SET enable_bitmapscan = off",
        "SET hnsw.ef_search = 40",
        "SET hnsw.iterative_scan = off",
        "SET hnsw.max_scan_tuples = 20000",
        "SET hnsw.scan_mem_multiplier = 1",
    ),
    "hnsw_iterative": (
        "SET work_mem = '64MB'",
        "SET enable_seqscan = off",
        "SET enable_bitmapscan = off",
        "SET hnsw.ef_search = 40",
        "SET hnsw.iterative_scan = strict_order",
        "SET hnsw.max_scan_tuples = 20000",
        "SET hnsw.scan_mem_multiplier = 1",
    ),
}


def configure_method_connection(connection: psycopg.Connection[Any], method: str) -> int:
    if method not in METHOD_SESSION_SETTINGS:
        raise ValueError(f"unknown method: {method}")
    with connection.cursor() as cursor:
        cursor.execute("LOAD 'vector'", prepare=False)
        for statement in (*COMMON_SESSION_SETTINGS, *METHOD_SESSION_SETTINGS[method]):
            cursor.execute(statement, prepare=False)
        cursor.execute("SELECT pg_backend_pid()")
        return int(cursor.fetchone()[0])


def search_sql(method: str, threshold: int, k: int) -> str:
    if threshold not in {1, 5, 10, 20, 50}:
        raise ValueError("filter threshold is not part of the frozen protocol")
    if method == "exact":
        return (
            f"SELECT id, embedding <-> %s::vector AS distance FROM {EXACT_TABLE} "
            f"WHERE filter_bucket < {threshold} ORDER BY distance, id LIMIT {k}"
        )
    if method in {"hnsw_standard", "hnsw_iterative"}:
        return (
            f"SELECT id, embedding <-> %s::vector AS distance FROM {HNSW_TABLE} "
            f"WHERE filter_bucket < {threshold} "
            f"ORDER BY distance LIMIT {k}"
        )
    raise ValueError(f"unknown method: {method}")


def search_parameters(method: str, vector: np.ndarray) -> tuple[np.ndarray, ...]:
    if method not in METHOD_SESSION_SETTINGS:
        raise ValueError(f"unknown method: {method}")
    return (vector,)


@dataclass
class TimedResult:
    rows: list[tuple[int, float]]
    duration_ns: int
    error_type: str | None = None
    error_message: str | None = None


def timed_execute_fetch(
    cursor: Any,
    sql: str,
    parameters: Sequence[Any],
    *,
    clock: Callable[[], int] = time.perf_counter_ns,
) -> TimedResult:
    started = clock()
    try:
        cursor.execute(sql, parameters, prepare=True)
        raw_rows = cursor.fetchall()
    except Exception as error:
        duration = clock() - started
        return TimedResult([], duration, type(error).__name__, str(error))
    duration = clock() - started
    rows = [(int(identifier), float(distance)) for identifier, distance in raw_rows]
    return TimedResult(rows, duration)


def session_settings(connection: psycopg.Connection[Any]) -> dict[str, str]:
    names = (
        "hnsw.ef_search",
        "hnsw.iterative_scan",
        "hnsw.max_scan_tuples",
        "hnsw.scan_mem_multiplier",
        "work_mem",
        "jit",
        "enable_seqscan",
        "enable_bitmapscan",
        "enable_indexscan",
        "enable_indexonlyscan",
        "plan_cache_mode",
        "statement_timeout",
    )
    with connection.cursor() as cursor:
        result: dict[str, str] = {}
        for name in names:
            cursor.execute("SELECT current_setting(%s)", (name,))
            result[name] = str(cursor.fetchone()[0])
        return result


def postgres_settings(connection: psycopg.Connection[Any]) -> list[dict[str, str]]:
    with connection.cursor() as cursor:
        cursor.execute("SHOW ALL")
        return [
            {"name": str(row[0]), "setting": str(row[1]), "description": str(row[2])}
            for row in cursor.fetchall()
        ]


def host_environment() -> dict[str, Any]:
    virtual_memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(ROOT))
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "physical_cpu_count": psutil.cpu_count(logical=False),
        "memory_total_bytes": virtual_memory.total,
        "memory_available_bytes": virtual_memory.available,
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "process_max_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "python_dependencies": {
            name: importlib.metadata.version(name)
            for name in ("h5py", "numpy", "pgvector", "psycopg", "psycopg-binary", "psutil")
        },
    }


def evict_shared_buffers(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    """Qualification-only substitute for restart when process signals are unavailable."""
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_buffercache", prepare=False)
        cursor.execute("CHECKPOINT", prepare=False)
        cursor.execute("SELECT * FROM pg_buffercache_summary()", prepare=False)
        before_row = cursor.fetchone()
        cursor.execute(
            """
WITH buffers AS MATERIALIZED (SELECT bufferid FROM pg_buffercache)
SELECT
  count(*) FILTER (WHERE evicted),
  count(*) FILTER (WHERE NOT evicted)
FROM (
  SELECT pg_buffercache_evict(bufferid) AS evicted
  FROM buffers
) attempts
""",
            prepare=False,
        )
        evicted, not_evicted = cursor.fetchone()
        cursor.execute("SELECT * FROM pg_buffercache_summary()", prepare=False)
        after_row = cursor.fetchone()
    if after_row[0] != 0:
        raise AssertionError("qualification shared-buffer eviction did not empty shared buffers")
    return {
        "method": "pg_buffercache_evict over a materialized buffer-id snapshot after CHECKPOINT",
        "reason": (
            "qualification host sandbox denied signals/new shared-memory allocation for a "
            "server restart; the final benchmark protocol still requires restart"
        ),
        "operating_system_cache_flushed": False,
        "before": {
            "buffers_used": before_row[0],
            "buffers_unused": before_row[1],
            "buffers_dirty": before_row[2],
            "buffers_pinned": before_row[3],
            "usagecount_avg": before_row[4],
        },
        "eviction_attempts": {"evicted": evicted, "not_evicted": not_evicted},
        "after": {
            "buffers_used": after_row[0],
            "buffers_unused": after_row[1],
            "buffers_dirty": after_row[2],
            "buffers_pinned": after_row[3],
            "usagecount_avg": after_row[4],
        },
    }
