#!/usr/bin/env python3
"""Read-only full-100k repetition diagnostics; never rerun or correct benchmarks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("exact", "hnsw_standard", "hnsw_iterative")
FILTERS = (1, 5, 10, 20, 50)
WARNING = (
    "Offline descriptive sensitivity diagnostic, not a corrected benchmark. "
    "All five repetitions remain the declared primary measurement. Later-four "
    "results are post-hoc sensitivity only. No significance, cache causality, "
    "cold/warm state, or final research conclusion is established. The same 200 "
    "queries are reused; repetitions and conditions are not independent samples."
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_snapshot(run: Path) -> dict[str, str]:
    """Independently check the producer manifest, including exact payload coverage."""
    if not run.is_dir() or (run / "ACTIVE").exists() or (run / "INVALID.json").exists():
        raise ValueError("input must be a finalized successful run")
    files = sorted(path for path in run.rglob("*") if path.is_file())
    if any(path.is_symlink() for path in run.rglob("*")):
        raise ValueError("symlinks are not accepted in run artifacts")
    observed = {str(path.relative_to(run)): sha256(path) for path in files}
    if "COMPLETE.json" not in observed or "checksums.sha256" not in observed:
        raise ValueError("completion marker and checksum manifest are required")
    expected = {}
    for line in (run / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name in expected or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid or duplicate checksum entry")
        expected[name] = digest
    payload = {name: digest for name, digest in observed.items()
               if Path(name).name not in {"checksums.sha256", "COMPLETE.json"}}
    if expected != payload:
        raise ValueError("input artifact checksum or coverage mismatch")
    return observed


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def integer(value, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def percentile(values: list[float], fraction: float) -> float:
    """Linear interpolation at (n-1)*fraction; not an individual-request p95."""
    ordered = sorted(values)
    if not ordered or not 0 <= fraction <= 1:
        raise ValueError("percentile requires values and a fraction in [0,1]")
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize_condition(queries: dict[int, dict[int, dict]]) -> dict:
    ordered = [queries[key] for key in sorted(queries)]
    all_five = [statistics.median(q[r]["duration_ns"] for r in range(1, 6)) for q in ordered]
    later_four = [statistics.median(q[r]["duration_ns"] for r in range(2, 6)) for q in ordered]
    ratios = [q[1]["duration_ns"] / later for q, later in zip(ordered, later_four)]
    identical = sum(len({tuple(q[r]["result_ids"]) for r in range(1, 6)}) == 1 for q in ordered)
    return {
        "query_count": len(queries),
        "repetition_median_ms": [statistics.median(q[r]["duration_ns"] for q in ordered) / 1e6
                                 for r in range(1, 6)],
        "median_paired_first_over_later_four": statistics.median(ratios),
        "fraction_queries_first_slower_than_later_four_median": sum(r > 1 for r in ratios) / len(ratios),
        "all_five_declared": {"median_query_median_ms": statistics.median(all_five) / 1e6,
                              "p95_query_median_ms": percentile(all_five, .95) / 1e6},
        "later_four_sensitivity_only": {"median_query_median_ms": statistics.median(later_four) / 1e6,
                                        "p95_query_median_ms": percentile(later_four, .95) / 1e6},
        "ordered_results_identical_queries": identical,
        "ordered_results_changed_queries": len(queries) - identical,
    }


def inspect_run(run: Path) -> tuple[dict, dict[str, str]]:
    snapshot = checked_snapshot(run)
    complete = read_json(run / "COMPLETE.json")
    manifest = read_json(run / "run_manifest.json")
    stage = read_json(run / "config.json")["stage"]
    round_number = integer(stage["experiment_round"], "round", 1)
    stage_id = f"benchmark-100k-round-{round_number}"
    if round_number not in (1, 2) or any(stage.get(k) != v for k, v in {
        "stage_id": stage_id, "scale_rows": 100000, "timed_query_count": 200,
        "campaign_id": "standalone-100k-v1",
        "repetitions": 5, "rounds": 1, "expected_timed_executions": 15000,
    }.items()):
        raise ValueError("input is not the complete standalone full-100k profile")
    if complete.get("valid") is not True or complete.get("qualification_only") is not False:
        raise ValueError("input is not marked valid full benchmark")
    for document in (complete, manifest):
        if (document.get("run_id"), document.get("stage_id"), document.get("experiment_round")) != (run.name, stage_id, round_number):
            raise ValueError("run identity mismatch")
    if complete.get("timed_executions") != 15000:
        raise ValueError("completion count mismatch")
    query_ids = read_json(run / "queries.json")["measured_query_ids"]
    if len(query_ids) != 200 or len(set(query_ids)) != 200:
        raise ValueError("expected 200 distinct measured queries")
    for query_id in query_ids:
        integer(query_id, "query ID")
    groups = defaultdict(lambda: defaultdict(dict))
    build_id = f"{run.name}-round-{round_number}-build-1"
    count = 0
    with (run / "executions.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            method, threshold = row["method"], integer(row["filter_threshold"], "filter", 1)
            query, repetition = integer(row["query_id"], "query ID"), integer(row["repetition"], "repetition", 1)
            integer(row["duration_ns"], "duration", 1)
            if method not in METHODS or threshold not in FILTERS or query not in query_ids or repetition not in range(1, 6):
                raise ValueError("execution outside the required grid")
            if any(row.get(k) != v for k, v in {"run_id": run.name, "stage_id": stage_id,
                "round": round_number, "build_id": build_id, "scale_rows": 100000, "k": 10}.items()):
                raise ValueError("execution build/run identity mismatch")
            if not {"error_type", "error_message", "timeout"}.issubset(row) or row.get("error_type") is not None or row.get("error_message") is not None or row.get("timeout") is not False:
                raise ValueError("execution errors are not permitted")
            ids = row["result_ids"]
            if not isinstance(ids, list) or len(ids) > 10 or len(ids) != len(set(ids)) or row.get("returned_count") != len(ids):
                raise ValueError("invalid ordered result IDs")
            for identifier in ids:
                integer(identifier, "result ID")
            if repetition in groups[(method, threshold)][query]:
                raise ValueError("duplicate execution key")
            groups[(method, threshold)][query][repetition] = row
            count += 1
    if count != 15000 or set(groups) != {(m, t) for m in METHODS for t in FILTERS}:
        raise ValueError("incomplete method/filter grid")
    for queries in groups.values():
        if set(queries) != set(query_ids) or any(set(q) != set(range(1, 6)) for q in queries.values()):
            raise ValueError("incomplete query/repetition grid")
    conditions = [{"method": m, "filter_threshold": t, **summarize_condition(groups[(m, t)])}
                  for m in METHODS for t in FILTERS]
    return {"run_id": run.name, "run_path": str(run), "round": round_number,
            "build_id": build_id, "source_commit": manifest["git_at_start"]["commit"],
            "measured_query_ids": query_ids, "timed_executions": count,
            "conditions": conditions, "input_sha256": snapshot}, snapshot


def diagnose(run_paths: list[Path]) -> dict:
    paths = [path.resolve() for path in run_paths]
    if len(paths) != 2 or len(set(paths)) != 2:
        raise ValueError("exactly two distinct run directories are required")
    inspected = [inspect_run(path) for path in paths]
    runs = sorted((result for result, _ in inspected), key=lambda value: value["round"])
    if [r["round"] for r in runs] != [1, 2] or runs[0]["measured_query_ids"] != runs[1]["measured_query_ids"]:
        raise ValueError("require rounds 1 and 2 with identical measured query selection")
    for path, (_, before) in zip(paths, inspected):
        if checked_snapshot(path) != before:
            raise ValueError("input artifacts changed during diagnostic")
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    return {"schema_version": 1, "interpretation": WARNING,
            "formulas": {"paired_ratio": "median_query(first_ns / median_query(repetitions_2_to_5_ns))",
                         "p95": "linear interpolation at (n-1)*0.95 across per-query medians",
                         "fraction": "number of queries with first_ns > later-four median_ns / 200"},
            "provenance": {"generator_path": str(Path(__file__).resolve()),
                           "generator_sha256": sha256(Path(__file__)), "repository_head": git("rev-parse", "HEAD"),
                           "git_status_porcelain": git("status", "--porcelain=v1").splitlines(),
                           "input_checksums_verified_before_and_after": True}, "runs": runs}


def markdown(report: dict) -> str:
    lines = ["# Full-100k repetition sensitivity audit", "", WARNING, "",
             "Each row contains 200 paired queries. Ratios are medians of per-query ratios, not ratios of condition medians.", "",
             "Later-four summaries intentionally retain fractional-nanosecond medians; no observations are removed from the source.", ""]
    for run in report["runs"]:
        lines += [f"## Round {run['round']}: {run['run_id']}", "", f"Build: `{run['build_id']}`", "",
                  "| Method | Filter | Repetition medians 1–5 (ms) | Paired first/later ratio | First slower | All-five median / p95 (ms) | Later-four sensitivity median / p95 (ms) | Identical ordered results |",
                  "|---|---:|---|---:|---:|---|---|---:|"]
        for row in run["conditions"]:
            five, four = row["all_five_declared"], row["later_four_sensitivity_only"]
            medians = ", ".join(f"{v:.6f}" for v in row["repetition_median_ms"])
            lines.append(f"| {row['method']} | {row['filter_threshold']}% | {medians} | {row['median_paired_first_over_later_four']:.6f} | "
                         f"{row['fraction_queries_first_slower_than_later_four_median']:.1%} | {five['median_query_median_ms']:.6f} / {five['p95_query_median_ms']:.6f} | "
                         f"{four['median_query_median_ms']:.6f} / {four['p95_query_median_ms']:.6f} | {row['ordered_results_identical_queries']}/200 |")
        lines.append("")
    lines += ["## Provenance", "", f"Repository HEAD: `{report['provenance']['repository_head']}`.", "",
              "Full input hashes, generator hash, build identities and worktree status are in `diagnostic.json`. This diagnostic does not replace the existing source/plan/recall verification.", ""]
    return "\n".join(lines)


def generate(run_paths: list[Path], output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing existing output directory: {output}")
    if "raw_results" in output.parts or any(output == p.resolve() or p.resolve() in output.parents for p in run_paths):
        raise ValueError("diagnostic output must be outside raw results and input runs")
    report = diagnose(run_paths)
    output.mkdir(parents=True, exist_ok=False)
    # Exclusive writes; a failure leaves partial diagnostic evidence intact.
    with (output / "diagnostic.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    with (output / "REPETITION_SENSITIVITY.md").open("x", encoding="utf-8") as handle:
        handle.write(markdown(report))
    for run in report["runs"]:
        if checked_snapshot(Path(run["run_path"])) != run["input_sha256"]:
            raise ValueError("input artifacts changed before diagnostic completion")
    checksums = output / "checksums.sha256"
    with checksums.open("x", encoding="utf-8") as handle:
        for name in ("diagnostic.json", "REPETITION_SENSITIVITY.md"):
            handle.write(f"{sha256(output / name)}  {name}\n")
    with (output / "COMPLETE.json").open("x", encoding="utf-8") as handle:
        json.dump({"schema_version": 1, "artifact_type": "offline_repetition_sensitivity_diagnostic",
                   "success": True, "checksums_sha256": sha256(checksums)}, handle, sort_keys=True)
        handle.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs=2, type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.runs, args.output)
    print(args.output.resolve())
