"""Exclusive, append-only artifact handling for Milestone 2 runs."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "raw_results" / "milestone_2"
ACTIVE_MARKER = "ACTIVE"


def make_run_id(config_sha256: str, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{config_sha256[:12]}"


def create_run_directory(config_sha256: str, run_id: str | None = None) -> Path:
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    destination = RUNS_ROOT / (run_id or make_run_id(config_sha256))
    destination.mkdir(mode=0o755, parents=False, exist_ok=False)
    (destination / "plans").mkdir(exist_ok=False)
    (destination / ACTIVE_MARKER).touch(mode=0o644, exist_ok=False)
    return destination


def _assert_writable(run_dir: Path) -> None:
    if (run_dir / "COMPLETE.json").exists() or (run_dir / "INVALID.json").exists():
        raise RuntimeError(f"run is finalized and immutable: {run_dir}")
    if not (run_dir / ACTIVE_MARKER).is_file():
        raise RuntimeError(f"run has no active-write marker: {run_dir}")


def write_bytes_exclusive(path: Path, payload: bytes) -> None:
    _assert_writable(path.parent if path.parent.name != "plans" else path.parent.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def write_json_exclusive(path: Path, value: Any) -> None:
    write_bytes_exclusive(path, canonical_json_bytes(value))


def write_jsonl_exclusive(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    payload = b"".join(canonical_json_bytes(row) for row in rows)
    write_bytes_exclusive(path, payload)


def _write_final_json_exclusive(path: Path, value: Any) -> None:
    """Write a terminal marker only after ACTIVE has been removed."""
    run_dir = path.parent
    if (run_dir / ACTIVE_MARKER).exists():
        raise RuntimeError("terminal marker cannot be written while run is ACTIVE")
    if (run_dir / "COMPLETE.json").exists() or (run_dir / "INVALID.json").exists():
        raise RuntimeError(f"run is already finalized: {run_dir}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_checksums(run_dir: Path) -> dict[str, str]:
    excluded = {ACTIVE_MARKER, "checksums.sha256", "COMPLETE.json", "INVALID.json"}
    paths = sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file() and path.name not in excluded
    )
    return {str(path.relative_to(run_dir)): sha256_file(path) for path in paths}


def write_checksum_manifest(run_dir: Path) -> dict[str, str]:
    checksums = payload_checksums(run_dir)
    lines = [f"{digest}  {name}\n" for name, digest in checksums.items()]
    write_bytes_exclusive(run_dir / "checksums.sha256", "".join(lines).encode("utf-8"))
    return checksums


def verify_checksum_manifest(run_dir: Path) -> None:
    expected: dict[str, str] = {}
    with (run_dir / "checksums.sha256").open(encoding="utf-8") as handle:
        for line in handle:
            digest, name = line.rstrip("\n").split("  ", maxsplit=1)
            expected[name] = digest
    observed = payload_checksums(run_dir)
    if observed != expected:
        raise AssertionError("run artifact checksum verification failed")


def finalize_complete(run_dir: Path, details: dict[str, Any]) -> None:
    _assert_writable(run_dir)
    if (run_dir / "checksums.sha256").exists():
        verify_checksum_manifest(run_dir)
    else:
        write_checksum_manifest(run_dir)
    (run_dir / ACTIVE_MARKER).unlink()
    try:
        _write_final_json_exclusive(run_dir / "COMPLETE.json", details)
    except BaseException:
        (run_dir / ACTIVE_MARKER).touch(mode=0o644, exist_ok=True)
        raise


def finalize_invalid(run_dir: Path, details: dict[str, Any]) -> None:
    _assert_writable(run_dir)
    checksum_path = run_dir / "checksums.sha256"
    if checksum_path.exists():
        checksum_path.unlink()
    write_checksum_manifest(run_dir)
    (run_dir / ACTIVE_MARKER).unlink()
    try:
        _write_final_json_exclusive(run_dir / "INVALID.json", details)
    except BaseException:
        (run_dir / ACTIVE_MARKER).touch(mode=0o644, exist_ok=True)
        raise
