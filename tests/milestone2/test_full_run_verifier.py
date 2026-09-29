"""Regression fixtures for full-100k restart and independent-round evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.milestone2.artifacts import payload_checksums
from experiments.milestone2.config import canonical_json_bytes, load_config
from experiments.milestone2.ground_truth import make_ground_truth_record
from tests.milestone2 import verify_run as verifier


def cache_fixture(offset: int = 0) -> dict:
    before = {
        "postmaster_started_at": "2026-09-29T10:00:00+00:00",
        "system_identifier": "1234567890123456",
        "database": "filtered_vector_search",
        "server_version_num": "170011",
        "relations": [
            {"relation": name, "kind": kind, "oid": 1000 + offset + index,
             "filenode": 2000 + offset + index}
            for index, (name, kind) in enumerate(sorted(verifier.PHYSICAL_RELATIONS.items()))
        ],
    }
    after = copy.deepcopy(before)
    after["postmaster_started_at"] = "2026-09-29T10:10:00+00:00"
    return {
        "method": "postgresql_restart_required",
        "before": before, "after": after,
        "postmaster_restarted": True, "same_cluster_and_database": True,
        "physical_relations_unchanged": True, "checkpoint_before_restart": True,
        "operating_system_cache_flushed": False, "wait_duration_ns": 50_000_000,
        "poll_count": 3, "connection_failures": 1, "passed": True,
    }


class RestartEvidenceTests(unittest.TestCase):
    def test_full_rounds_use_their_declared_round_numbers(self) -> None:
        for round_number in (1, 2):
            config = load_config(verifier.ROOT / "config" / "milestone2" / f"benchmark-100k-round-{round_number}.json")
            self.assertTrue(config.is_full_benchmark)
            self.assertEqual(config.round_numbers, (round_number,))
            self.assertEqual(config.expected_execution_count, 15000)

    def test_actual_restart_with_unchanged_physical_graph_passes(self) -> None:
        verifier.verify_cache_evidence(cache_fixture(), full_benchmark=True)

    def test_buffer_eviction_is_allowed_only_for_qualification(self) -> None:
        cache = {"method": "pg_buffercache_evict", "after": {"buffers_used": 0}, "operating_system_cache_flushed": False}
        verifier.verify_cache_evidence(cache, full_benchmark=False)
        with self.assertRaisesRegex(AssertionError, "actual PostgreSQL restart"):
            verifier.verify_cache_evidence(cache, full_benchmark=True)

    def test_unchanged_or_earlier_postmaster_is_rejected(self) -> None:
        for after_time in ("2026-09-29T10:00:00+00:00", "2026-09-28T10:00:00+00:00"):
            with self.subTest(after_time=after_time):
                cache = cache_fixture()
                cache["after"]["postmaster_started_at"] = after_time
                with self.assertRaisesRegex(AssertionError, "later postmaster"):
                    verifier.verify_cache_evidence(cache, full_benchmark=True)

    def test_changed_cluster_or_rebuilt_graph_during_restart_is_rejected(self) -> None:
        for field in ("system_identifier", "database", "server_version_num", "relations"):
            with self.subTest(field=field):
                cache = cache_fixture()
                if field == "relations":
                    cache["after"][field][0]["oid"] += 99
                else:
                    cache["after"][field] = "different"
                with self.assertRaises(AssertionError):
                    verifier.verify_cache_evidence(cache, full_benchmark=True)

    def test_missing_relation_or_checkpoint_and_invalid_wait_are_rejected(self) -> None:
        for change in ("relation", "checkpoint", "wait"):
            with self.subTest(change=change):
                cache = cache_fixture()
                if change == "relation":
                    cache["before"]["relations"].pop()
                elif change == "checkpoint":
                    cache["checkpoint_before_restart"] = False
                else:
                    cache["wait_duration_ns"] = 0
                with self.assertRaises(AssertionError):
                    verifier.verify_cache_evidence(cache, full_benchmark=True)


class RoundPairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.first = self.make_run(1, 0)
        self.second = self.make_run(2, 100)

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_bytes(canonical_json_bytes(value))

    @staticmethod
    def refresh_checksums(path: Path) -> None:
        (path / "checksums.sha256").write_text(
            "".join(f"{digest}  {name}\n" for name, digest in payload_checksums(path).items()),
            encoding="utf-8",
        )

    def make_run(self, round_number: int, object_offset: int) -> Path:
        path = self.root / f"test-round-{round_number}"
        path.mkdir()
        stage = {
            "stage_id": f"benchmark-100k-round-{round_number}", "experiment_round": round_number,
            "scale_rows": 100000, "timed_query_count": 200, "repetitions": 5,
        }
        self.write_json(path / "config.json", {"stage": stage, "protocol": {"k": 10}})
        self.write_json(path / "run_manifest.json", {
            "git_at_start": {"commit": str(round_number) * 40},
            "started_at": f"2026-09-29T{9 + round_number * 2:02d}:00:00+00:00",
        })
        self.write_json(path / "COMPLETE.json", {"completed_at": f"2026-09-29T{10 + round_number * 2:02d}:00:00+00:00"})
        self.write_json(path / "dataset_manifest.json", {
            "sha256": "same-canonical-source", "byte_size": 525128288, "groups": {},
            "attributes": {"distance": "euclidean"}, "values_normalized": False,
            "base_ids_zero_based": True,
        })
        self.write_json(path / "scale_manifest.json", {"membership_sha256": "same-scale"})
        self.write_json(path / "queries.json", {"measured_query_ids": [123]})
        self.write_json(path / "database_evidence.json", {
            "source_vector_stream_sha256": "same-data", "ordered_vector_stream_sha256": "same-data",
            "rank_contract": {"distinct_ranks": 100000}, "filter_counts": {"1": 1000},
        })
        self.write_json(path / "cache_reset.json", cache_fixture(object_offset))
        record = make_ground_truth_record(
            run_id=path.name, scale_rows=100000, threshold=1, qualifying_count=1000,
            query_id=123, k=10, rows=[(i, float(i)) for i in range(10)],
            dataset_sha256="same-canonical-source", scale_manifest_sha256="same-scale",
        )
        (path / "ground_truth.jsonl").write_bytes(canonical_json_bytes(record))
        self.refresh_checksums(path)
        return path

    def verify_pair(self) -> dict:
        # Isolate the cross-round logic; verify_run has its own full source-data
        # validation and is deliberately not replaced by this small fixture.
        with patch.object(verifier, "verify_run", return_value={"passed": True, "timed_executions": 15000}), patch.object(
            verifier, "source_blob_identity", return_value={"experiments/milestone2/runner.py": "100644:same-code"}
        ):
            return verifier.verify_round_pair(self.first, self.second)

    def test_distinct_builds_with_identical_data_and_ground_truth_pass(self) -> None:
        result = self.verify_pair()
        self.assertTrue(result["passed"])
        self.assertEqual(result["total_timed_executions"], 30000)
        self.assertEqual(result["ground_truth_records_equal"], 1)
        self.assertEqual(len(result["physical_rebuild_evidence"]), 6)
        self.assertFalse(result["research_conclusions_authorized"])

    def test_reused_hnsw_graph_is_rejected(self) -> None:
        cache = json.loads((self.second / "cache_reset.json").read_text())
        first_cache = cache_fixture()
        old = next(row for row in first_cache["before"]["relations"] if row["relation"] == "sift_hnsw_embedding_idx")
        for boundary in ("before", "after"):
            row = next(row for row in cache[boundary]["relations"] if row["relation"] == "sift_hnsw_embedding_idx")
            row.update(old)
        self.write_json(self.second / "cache_reset.json", cache)
        self.refresh_checksums(self.second)
        with self.assertRaisesRegex(AssertionError, "physical object was reused"):
            self.verify_pair()

    def test_changed_physical_data_is_rejected(self) -> None:
        path = self.second / "database_evidence.json"
        data = json.loads(path.read_text())
        data["ordered_vector_stream_sha256"] = "changed-data"
        self.write_json(path, data)
        self.refresh_checksums(self.second)
        with self.assertRaisesRegex(AssertionError, "physical data evidence differs"):
            self.verify_pair()

    def test_changed_ground_truth_is_rejected_despite_valid_record_checksum(self) -> None:
        record = make_ground_truth_record(
            run_id=self.second.name, scale_rows=100000, threshold=1, qualifying_count=1000,
            query_id=123, k=10, rows=[(i, float(i + 1)) for i in range(10)],
            dataset_sha256="same-canonical-source", scale_manifest_sha256="same-scale",
        )
        (self.second / "ground_truth.jsonl").write_bytes(canonical_json_bytes(record))
        self.refresh_checksums(self.second)
        with self.assertRaisesRegex(AssertionError, "ground truth changed"):
            self.verify_pair()

    def test_experiment_source_changes_are_rejected(self) -> None:
        with patch.object(verifier, "verify_run", return_value={"passed": True}), patch.object(
            verifier, "source_blob_identity", side_effect=[{"runner.py": "old"}, {"runner.py": "new"}]
        ):
            with self.assertRaisesRegex(AssertionError, "source code/configuration changed"):
                verifier.verify_round_pair(self.first, self.second)

    def test_reversed_rounds_are_rejected(self) -> None:
        with patch.object(verifier, "verify_run", return_value={"passed": True}):
            with self.assertRaisesRegex(AssertionError, "round-pair order"):
                verifier.verify_round_pair(self.second, self.first)


if __name__ == "__main__":
    unittest.main()
