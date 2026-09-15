#!/usr/bin/env python3
"""Download and validate the pinned ANN-Benchmarks SIFT1M HDF5 artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.milestone2.config import canonical_json_bytes  # noqa: E402
from experiments.milestone2.dataset import (  # noqa: E402
    DEFAULT_HDF5_PATH,
    LOCAL_MANIFEST_PATH,
    SOURCE_MANIFEST_PATH,
    validate_hdf5,
)


def download(url: str, destination: Path, expected_sha256: str) -> tuple[dict[str, object], dict[str, object]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    started = datetime.now(timezone.utc)
    request = urllib.request.Request(url, headers={"User-Agent": "filtered-vector-search-m2/1"})
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("xb") as handle:
        total = int(response.headers.get("Content-Length", "0"))
        copied = 0
        while True:
            chunk = response.read(4 * 1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            copied += len(chunk)
            if total:
                print(f"downloaded {copied}/{total} bytes", file=sys.stderr)
        handle.flush()
        os.fsync(handle.fileno())
    validation = validate_hdf5(temporary, expected_sha256=expected_sha256)
    temporary.replace(destination)
    validation["path"] = str(destination)
    acquisition = {
        "requested_url": url,
        "final_url": response.geturl(),
        "download_started_at": started.isoformat(),
        "download_completed_at": datetime.now(timezone.utc).isoformat(),
    }
    return acquisition, validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=DEFAULT_HDF5_PATH)
    args = parser.parse_args()

    source = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_sha = str(source["sha256"])
    acquisition: dict[str, object]
    if args.destination.exists():
        previous = (
            json.loads(LOCAL_MANIFEST_PATH.read_text(encoding="utf-8"))
            if LOCAL_MANIFEST_PATH.exists()
            else {}
        )
        acquisition = {
            "requested_url": source["canonical_url"],
            "final_url": previous.get("final_url", source["canonical_url"]),
            "download_started_at": previous.get("download_started_at"),
            "download_completed_at": previous.get("download_completed_at"),
            "reused_existing_file": True,
        }
        validation = validate_hdf5(args.destination, expected_sha256=expected_sha)
    else:
        acquisition, validation = download(
            str(source["canonical_url"]), args.destination, expected_sha
        )
    if int(validation["byte_size"]) != int(source["byte_size"]):
        raise SystemExit(
            f"SIFT1M size mismatch: expected {source['byte_size']}, got {validation['byte_size']}"
        )
    local = {
        **acquisition,
        **validation,
        "canonical_url": source["canonical_url"],
        "expected_sha256": expected_sha,
    }
    LOCAL_MANIFEST_PATH.write_bytes(canonical_json_bytes(local))
    print(json.dumps(local, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
