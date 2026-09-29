from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from experiments.milestone2 import artifacts
from experiments.milestone2.runner import require_clean_git_state, verify_milestone1_preserved


class ArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_run(self, run_id: str = "test-run") -> Path:
        with patch.object(artifacts, "RUNS_ROOT", self.root):
            return artifacts.create_run_directory("a" * 64, run_id=run_id)

    def test_run_id_contains_utc_timestamp_and_config_digest(self) -> None:
        when = datetime(2026, 9, 15, 12, 34, 56, tzinfo=timezone.utc)
        self.assertEqual(
            artifacts.make_run_id("abcdef0123456789", now=when),
            "20260915T123456Z_abcdef012345",
        )

    def test_run_directory_creation_is_exclusive(self) -> None:
        with patch.object(artifacts, "RUNS_ROOT", self.root):
            run = artifacts.create_run_directory("a" * 64, run_id="same")
            self.assertTrue((run / "plans").is_dir())
            self.assertTrue((run / artifacts.ACTIVE_MARKER).is_file())
            with self.assertRaises(FileExistsError):
                artifacts.create_run_directory("a" * 64, run_id="same")

    def test_write_requires_active_marker(self) -> None:
        run = self.make_run()
        (run / artifacts.ACTIVE_MARKER).unlink()
        with self.assertRaisesRegex(RuntimeError, "no active-write marker"):
            artifacts.write_json_exclusive(run / "config.json", {})

    def test_artifact_write_is_exclusive(self) -> None:
        run = self.make_run()
        path = run / "config.json"
        artifacts.write_json_exclusive(path, {"version": 1})
        with self.assertRaises(FileExistsError):
            artifacts.write_json_exclusive(path, {"version": 2})

    def test_checksum_manifest_detects_payload_mutation(self) -> None:
        run = self.make_run()
        payload = run / "config.json"
        artifacts.write_json_exclusive(payload, {"version": 1})
        artifacts.write_json_exclusive(run / "plans" / "plan.json", [{"Plan": {}}])
        checksums = artifacts.write_checksum_manifest(run)
        self.assertEqual(set(checksums), {"config.json", "plans/plan.json"})
        artifacts.verify_checksum_manifest(run)
        payload.write_text('{"version":2}\n', encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "checksum verification failed"):
            artifacts.verify_checksum_manifest(run)

    def test_finalized_run_rejects_new_artifacts(self) -> None:
        run = self.make_run()
        artifacts.write_json_exclusive(run / "config.json", {"version": 1})
        artifacts.finalize_complete(run, {"valid": True})
        self.assertFalse((run / artifacts.ACTIVE_MARKER).exists())
        artifacts.verify_checksum_manifest(run)
        with self.assertRaisesRegex(RuntimeError, "finalized and immutable"):
            artifacts.write_json_exclusive(run / "late.json", {})

    def test_invalid_run_is_preserved_and_immutable(self) -> None:
        run = self.make_run()
        artifacts.write_json_exclusive(run / "failure.json", {"phase": "plan"})
        artifacts.finalize_invalid(run, {"valid": False})
        self.assertTrue((run / "INVALID.json").is_file())
        self.assertFalse((run / artifacts.ACTIVE_MARKER).exists())
        with self.assertRaisesRegex(RuntimeError, "finalized and immutable"):
            artifacts.write_json_exclusive(run / "replacement.json", {})

    def test_refinalization_preserves_every_completed_or_invalid_artifact(self) -> None:
        for first in (artifacts.finalize_complete, artifacts.finalize_invalid):
            for second in (artifacts.finalize_complete, artifacts.finalize_invalid):
                with self.subTest(first=first.__name__, second=second.__name__):
                    run = self.make_run(f"{first.__name__}-{second.__name__}")
                    artifacts.write_json_exclusive(run / "config.json", {"version": 1})
                    first(run, {"terminal_state": first.__name__})
                    before = {
                        str(path.relative_to(run)): path.read_bytes()
                        for path in run.rglob("*") if path.is_file()
                    }
                    with self.assertRaisesRegex(RuntimeError, "finalized and immutable"):
                        second(run, {"terminal_state": second.__name__})
                    after = {
                        str(path.relative_to(run)): path.read_bytes()
                        for path in run.rglob("*") if path.is_file()
                    }
                    self.assertEqual(before, after)
                    artifacts.verify_checksum_manifest(run)

    def test_finalization_without_active_marker_preserves_existing_checksums(self) -> None:
        for finalize in (artifacts.finalize_complete, artifacts.finalize_invalid):
            with self.subTest(finalize=finalize.__name__):
                run = self.make_run(f"inactive-{finalize.__name__}")
                artifacts.write_json_exclusive(run / "config.json", {"version": 1})
                artifacts.write_checksum_manifest(run)
                (run / artifacts.ACTIVE_MARKER).unlink()
                before = {
                    path.name: path.read_bytes() for path in run.iterdir() if path.is_file()
                }
                with self.assertRaisesRegex(RuntimeError, "no active-write marker"):
                    finalize(run, {"valid": False})
                self.assertEqual(
                    before,
                    {path.name: path.read_bytes() for path in run.iterdir() if path.is_file()},
                )
                artifacts.verify_checksum_manifest(run)


class MilestoneOnePreservationTests(unittest.TestCase):
    def test_tracked_milestone1_raw_outputs_match_accepted_commit(self) -> None:
        result = verify_milestone1_preserved()
        self.assertTrue(result["preserved"])
        self.assertEqual(
            result["baseline_commit"], "cd199a2b523b875ab06a8de00953e17672a2800a"
        )
        self.assertGreater(len(result["checked_files"]), 0)

    def test_qualification_launch_rejects_dirty_git_state(self) -> None:
        require_clean_git_state({"dirty": False, "status_porcelain": []})
        with self.assertRaisesRegex(RuntimeError, "clean committed Git state"):
            require_clean_git_state(
                {"dirty": True, "status_porcelain": [" M experiments/runner.py"]}
            )


if __name__ == "__main__":
    unittest.main()
