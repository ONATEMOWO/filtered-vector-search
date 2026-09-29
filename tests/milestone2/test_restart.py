from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg

from experiments.milestone2.config import load_config
from experiments.milestone2.restart import (
    EXPECTED_RELATIONS,
    validate_completed_restart,
    validate_identity,
    wait_for_restart,
)
from experiments.milestone2.runner import build_resource_projection


ROOT = Path(__file__).resolve().parents[2]


def identity(started_at: str = "2026-09-29T12:00:00+00:00") -> dict[str, object]:
    return {
        "postmaster_started_at": started_at,
        "system_identifier": "12345",
        "database": "filtered_vector_search",
        "server_version_num": "170011",
        "relations": [
            {"relation": name, "oid": 100 + index, "filenode": 200 + index, "kind": kind}
            for index, (name, kind) in enumerate(sorted(EXPECTED_RELATIONS.items()))
        ],
    }


class FakeTime:
    def __init__(self) -> None:
        self.now_ns = 0

    def clock(self) -> int:
        self.now_ns += 1_000
        return self.now_ns

    def sleep(self, seconds: float) -> None:
        self.now_ns += int(seconds * 1_000_000_000)


class FakeConnection:
    def __init__(self, snapshot: dict[str, object]) -> None:
        self.snapshot = snapshot
        self.closed = False

    def close(self) -> None:
        self.closed = True


class RestartTests(unittest.TestCase):
    def test_new_postmaster_on_unchanged_cluster_and_objects_is_accepted(self) -> None:
        validate_completed_restart(identity(), identity("2026-09-29T12:01:00+00:00"))

    def test_unchanged_or_older_postmaster_is_rejected(self) -> None:
        for timestamp in ("2026-09-29T12:00:00+00:00", "2026-09-29T11:59:00+00:00"):
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(AssertionError, "has not restarted"):
                validate_completed_restart(identity(), identity(timestamp))

    def test_changed_cluster_database_version_or_physical_graph_is_rejected(self) -> None:
        for field, value in (
            ("system_identifier", "67890"),
            ("database", "different_database"),
            ("server_version_num", "180000"),
        ):
            with self.subTest(field=field):
                changed = identity("2026-09-29T12:01:00+00:00")
                changed[field] = value
                with self.assertRaisesRegex(AssertionError, f"changed {field}"):
                    validate_completed_restart(identity(), changed)
        for field in ("oid", "filenode"):
            with self.subTest(field=field):
                changed = identity("2026-09-29T12:01:00+00:00")
                changed["relations"][0][field] += 1_000
                with self.assertRaisesRegex(AssertionError, "changed relations"):
                    validate_completed_restart(identity(), changed)

    def test_missing_or_duplicate_physical_relations_are_rejected(self) -> None:
        missing = identity()
        missing["relations"].pop()
        duplicate = identity()
        duplicate["relations"][1]["oid"] = duplicate["relations"][0]["oid"]
        for snapshot in (missing, duplicate):
            with self.assertRaisesRegex(AssertionError, "six distinct"):
                validate_identity(snapshot)

    def test_wait_requires_real_restart_and_closes_every_observer_connection(self) -> None:
        clock = FakeTime()
        connections = [
            FakeConnection(identity()),
            FakeConnection(identity("2026-09-29T12:01:00+00:00")),
        ]
        remaining = iter(connections)
        messages: list[str] = []
        with patch("experiments.milestone2.restart.capture_restart_identity", side_effect=lambda connection: connection.snapshot):
            evidence = wait_for_restart(
                identity(), log=messages.append, timeout_seconds=10,
                connect_factory=lambda: next(remaining), clock_ns=clock.clock, sleep=clock.sleep,
            )
        self.assertTrue(all(connection.closed for connection in connections))
        self.assertEqual(evidence["method"], "postgresql_restart_required")
        self.assertEqual(evidence["poll_count"], 2)
        self.assertTrue(evidence["postmaster_restarted"])
        self.assertGreater(evidence["wait_duration_ns"], 0)
        self.assertFalse(evidence["operating_system_cache_flushed"])
        self.assertTrue(any("stop &&" in message for message in messages))

    def test_wait_records_temporary_connection_failure_during_restart(self) -> None:
        clock = FakeTime()
        after = FakeConnection(identity("2026-09-29T12:01:00+00:00"))
        attempts = iter([psycopg.OperationalError("server stopped"), after])

        def connect() -> FakeConnection:
            result = next(attempts)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("experiments.milestone2.restart.capture_restart_identity", side_effect=lambda connection: connection.snapshot):
            evidence = wait_for_restart(
                identity(), log=lambda message: None, timeout_seconds=10,
                connect_factory=connect, clock_ns=clock.clock, sleep=clock.sleep,
            )
        self.assertEqual(evidence["connection_failures"], 1)
        self.assertTrue(after.closed)

    def test_wait_fails_closed_if_restart_is_not_observed(self) -> None:
        clock = FakeTime()
        with patch("experiments.milestone2.restart.capture_restart_identity", return_value=identity()):
            with self.assertRaisesRegex(TimeoutError, "required PostgreSQL restart"):
                wait_for_restart(
                    identity(), log=lambda message: None, timeout_seconds=3,
                    connect_factory=lambda: FakeConnection(identity()),
                    clock_ns=clock.clock, sleep=clock.sleep,
                )

    def test_restart_operator_wait_is_excluded_from_compute_projection(self) -> None:
        config = load_config(ROOT / "config/milestone2/qualification-100k.json")
        phases = {name: 100 for name in (
            "source_scale_read_ns", "copy_exact_ns", "copy_hnsw_from_exact_ns",
            "exact_index_ns", "hnsw_build_ns", "vacuum_analyze_checkpoint_ns",
            "ground_truth_generation_ns", "ground_truth_determinism_reexecution_ns",
            "independent_ground_truth_validation_ns", "shared_buffer_reset_ns",
        )}
        phases.update(timed_workload_and_warmups_ns=500, total_before_final_artifacts_ns=2_000)
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "plans").mkdir()
            for name in ("executions.jsonl", "warmups.jsonl", "ground_truth.jsonl", "plans/one.json"):
                (run_dir / name).write_bytes(b"data")
            baseline = build_resource_projection(config, phases, [{"duration_ns": 10}], [], run_dir)
            with_wait = copy.deepcopy(phases)
            with_wait["restart_wait_ns"] = 60_000_000_000
            with_wait["total_before_final_artifacts_ns"] += with_wait["restart_wait_ns"]
            observed = build_resource_projection(config, with_wait, [{"duration_ns": 10}], [], run_dir)
        self.assertEqual(observed["estimated_full_pipeline_seconds"], baseline["estimated_full_pipeline_seconds"])
        self.assertEqual(observed["excluded_operator_restart_wait_ns"], 60_000_000_000)


if __name__ == "__main__":
    unittest.main()
