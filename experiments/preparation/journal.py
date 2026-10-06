"""Exclusive, fsynced pass checkpoints outside individual query timers.

Completed passes survive later failures. Caught interruptions preserve the active
pass's completed observations too. A hard process kill may lose the active pass;
this is bounded checkpointing, not a claim of zero-loss transactional storage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from experiments.milestone2.artifacts import sha256_file, write_jsonl_exclusive


class CheckpointJournal:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.chunks: list[dict[str, Any]] = []

    def capture(self, name: str, phase: str, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        if Path(name).name != name or not name.endswith(".jsonl"):
            raise ValueError("checkpoint must be a root-level JSONL filename")
        if (self.run_dir / name).exists():
            raise FileExistsError(self.run_dir / name)
        buffered: list[dict[str, Any]] = []
        try:
            for row in rows:
                if row.get("phase") != phase:
                    raise AssertionError("checkpoint phase differs from row")
                buffered.append(row)
        except BaseException:
            # Do not disguise an interrupted pass as a complete checkpoint.
            if buffered:
                partial = name.removesuffix(".jsonl") + ".partial.jsonl"
                write_jsonl_exclusive(self.run_dir / partial, buffered)
            raise
        if not buffered:
            raise AssertionError("empty checkpoint")
        write_jsonl_exclusive(self.run_dir / name, buffered)
        self.chunks.append({
            "file": name, "phase": phase, "row_count": len(buffered),
            "first_sequence_index": buffered[0]["sequence_index"],
            "last_sequence_index": buffered[-1]["sequence_index"],
            "sha256": sha256_file(self.run_dir / name),
        })
        return buffered

    def consolidate(self, phases: set[str], destination: str) -> list[dict[str, Any]]:
        if Path(destination).name != destination or not destination.endswith(".jsonl"):
            raise ValueError("consolidation must be a root-level JSONL filename")
        rows: list[dict[str, Any]] = []
        for chunk in self.chunks:
            if chunk["phase"] not in phases:
                continue
            path = self.run_dir / chunk["file"]
            if sha256_file(path) != chunk["sha256"]:
                raise AssertionError("checkpoint changed before consolidation")
            batch = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            if len(batch) != chunk["row_count"] or any(row["phase"] != chunk["phase"] for row in batch):
                raise AssertionError("checkpoint metadata differs from payload")
            rows.extend(batch)
        indices = [row["sequence_index"] for row in rows]
        if not rows or indices != sorted(set(indices)):
            raise AssertionError("consolidation contains empty, duplicate or reordered observations")
        write_jsonl_exclusive(self.run_dir / destination, rows)
        return rows
