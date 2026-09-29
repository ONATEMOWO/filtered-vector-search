"""Fail-closed verification of the real PostgreSQL restart required for full runs."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

import psycopg

from .database import connection_parameters


EXPECTED_RELATIONS = {
    "sift_exact": "r",
    "sift_hnsw": "r",
    "sift_exact_pkey": "i",
    "sift_hnsw_pkey": "i",
    "sift_exact_filter_bucket_idx": "i",
    "sift_hnsw_embedding_idx": "i",
}


def capture_restart_identity(connection: Any) -> dict[str, Any]:
    """Read cluster and physical-object identity without scanning the vector data."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_postmaster_start_time(), "
            "(pg_control_system()).system_identifier::text, "
            "current_database(), current_setting('server_version_num')",
            prepare=False,
        )
        started_at, system_identifier, database, server_version_num = cursor.fetchone()
        cursor.execute(
            "SELECT c.relname, c.oid::bigint, pg_relation_filenode(c.oid)::bigint, c.relkind "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='milestone2' AND c.relkind IN ('r', 'i') ORDER BY c.relname",
            prepare=False,
        )
        relations = [
            {"relation": name, "oid": int(oid), "filenode": int(filenode), "kind": kind}
            for name, oid, filenode, kind in cursor.fetchall()
        ]
    identity = {
        "postmaster_started_at": started_at.astimezone(timezone.utc).isoformat(),
        "system_identifier": str(system_identifier),
        "database": str(database),
        "server_version_num": str(server_version_num),
        "relations": relations,
    }
    validate_identity(identity)
    return identity


def validate_identity(identity: dict[str, Any]) -> None:
    relations = identity.get("relations", [])
    if (
        len(relations) != len(EXPECTED_RELATIONS)
        or {row["relation"]: row["kind"] for row in relations} != EXPECTED_RELATIONS
        or any(int(row["oid"]) <= 0 or int(row["filenode"]) <= 0 for row in relations)
        or len({row["oid"] for row in relations}) != len(relations)
        or len({row["filenode"] for row in relations}) != len(relations)
    ):
        raise AssertionError("restart identity lacks the six distinct physical benchmark relations")
    if not identity.get("system_identifier") or not identity.get("database"):
        raise AssertionError("restart identity lacks its cluster or database")
    started = datetime.fromisoformat(identity["postmaster_started_at"])
    if started.tzinfo is None:
        raise AssertionError("postmaster start timestamp must contain a timezone")


def validate_identity_continuity(before: dict[str, Any], after: dict[str, Any]) -> None:
    validate_identity(before)
    validate_identity(after)
    for field in ("system_identifier", "database", "server_version_num", "relations"):
        if before[field] != after[field]:
            raise AssertionError(f"PostgreSQL restart changed {field}")


def validate_completed_restart(before: dict[str, Any], after: dict[str, Any]) -> None:
    validate_identity_continuity(before, after)
    if datetime.fromisoformat(after["postmaster_started_at"]) <= datetime.fromisoformat(
        before["postmaster_started_at"]
    ):
        raise AssertionError("PostgreSQL postmaster has not restarted after preparation")


def _connect_for_restart() -> Any:
    parameters = {**connection_parameters(), "connect_timeout": 3}
    return psycopg.connect(
        **parameters, application_name="m2-restart-observer", autocommit=True
    )


def wait_for_restart(
    before: dict[str, Any],
    *,
    log: Callable[[str], None],
    timeout_seconds: float = 900,
    poll_interval_seconds: float = 2,
    connect_factory: Callable[[], Any] = _connect_for_restart,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Wait for an operator restart; never substitute buffer eviction or rebuild."""
    validate_identity(before)
    if not 0 < timeout_seconds <= 900 or not 0 < poll_interval_seconds <= 10:
        raise ValueError("restart wait must be bounded to fifteen minutes with short polls")
    started_ns = clock_ns()
    deadline_ns = started_ns + int(timeout_seconds * 1_000_000_000)
    poll_count = 0
    connection_failures = 0
    log(
        "Preparation is complete. Restart PostgreSQL from the project directory now: "
        "./scripts/postgres_local.sh stop && ./scripts/postgres_local.sh start"
    )
    log(f"Waiting up to {timeout_seconds:g} seconds for a verified real PostgreSQL restart")
    while clock_ns() < deadline_ns:
        poll_count += 1
        connection = None
        try:
            connection = connect_factory()
            after = capture_restart_identity(connection)
        except (psycopg.OperationalError, psycopg.InterfaceError):
            connection_failures += 1
        else:
            validate_identity_continuity(before, after)
            after_time = datetime.fromisoformat(after["postmaster_started_at"])
            before_time = datetime.fromisoformat(before["postmaster_started_at"])
            if after_time < before_time:
                raise AssertionError("postmaster start time moved backwards")
            if after_time > before_time:
                validate_completed_restart(before, after)
                wait_duration_ns = clock_ns() - started_ns
                log("Verified newer PostgreSQL postmaster with the same cluster and physical graph")
                return {
                    "method": "postgresql_restart_required",
                    "before": before,
                    "after": after,
                    "postmaster_restarted": True,
                    "same_cluster_and_database": True,
                    "physical_relations_unchanged": True,
                    "checkpoint_before_restart": True,
                    "operating_system_cache_flushed": False,
                    "wait_duration_ns": wait_duration_ns,
                    "poll_count": poll_count,
                    "connection_failures": connection_failures,
                    "passed": True,
                }
        finally:
            if connection is not None:
                connection.close()
        remaining_seconds = (deadline_ns - clock_ns()) / 1_000_000_000
        if remaining_seconds > 0:
            sleep(min(poll_interval_seconds, remaining_seconds))
    raise TimeoutError("required PostgreSQL restart was not observed within the bounded wait")
