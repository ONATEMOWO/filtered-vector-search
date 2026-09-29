#!/usr/bin/env python3
"""Render descriptive qualification evidence from explicit, immutable run directories.

Example (after independently verifying both runs):
    .venv-milestone2/bin/python analysis/generate_assignment_figures.py \
        raw_results/milestone_2/RUN_10K raw_results/milestone_2/RUN_100K \
        --output-dir outputs/assignment_evidence

The script checks every source artifact checksum, recomputes the plotted
aggregates from executions.jsonl, and refuses to overwrite derived evidence.
It does not execute queries or modify source run directories.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.milestone2.artifacts import (  # noqa: E402
    sha256_file,
    verify_checksum_manifest,
)


METHODS = ("exact", "hnsw_standard", "hnsw_iterative")
METHOD_LABELS = ("Exact", "Standard HNSW", "Iterative HNSW (strict order)")
COLORS = ("#2463A7", "#D16D19", "#7153A1")
THRESHOLDS = (1, 5, 10, 20, 50)
FIGURES = (
    (
        "qualification_recall_at_10.png",
        "mean_canonical_recall_at_10",
        "Canonical Recall@10",
        "Mean query recall (fixed denominator 10)",
    ),
    (
        "qualification_result_completeness.png",
        "returned_k_rate",
        "Result completeness",
        "Fraction of executions returning 10 qualifying rows",
    ),
    (
        "qualification_client_latency.png",
        "median_latency_ns",
        "Client-observed execute-and-fetch latency",
        "Median of per-query median latencies (ms)",
    ),
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def recompute_conditions(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("error_type") is not None:
            raise ValueError("figures require a completed run without execution errors")
        if not all(
            row.get(key) is True
            for key in ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")
        ):
            raise ValueError("execution contains invalid returned rows")
        if int(row["k"]) != 10 or int(row["duration_ns"]) < 0:
            raise ValueError("execution has invalid k or duration")
        for key in ("canonical_recall_at_10", "tie_aware_recall_at_10"):
            value = float(row[key])
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("execution has an invalid recall value")
        returned_count = int(row["returned_count"])
        if not 0 <= returned_count <= 10 or bool(row["returned_k"]) != (returned_count == 10):
            raise ValueError("execution completeness fields disagree")
        groups[(str(row["method"]), int(row["filter_threshold"]))].append(row)
    expected = {(method, threshold) for method in METHODS for threshold in THRESHOLDS}
    if set(groups) != expected:
        raise ValueError("all three methods and five filter conditions are required")
    conditions: dict[tuple[str, int], dict[str, Any]] = {}
    for key, condition_rows in groups.items():
        per_query: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in condition_rows:
            per_query[int(row["query_id"])].append(row)
        query_medians = [
            int(statistics.median(int(row["duration_ns"]) for row in query_rows))
            for query_rows in per_query.values()
        ]
        conditions[key] = {
            "execution_samples": len(condition_rows),
            "query_samples": len(per_query),
            "median_latency_ns": int(statistics.median(query_medians)),
            "mean_canonical_recall_at_10": statistics.fmean(
                statistics.fmean(float(row["canonical_recall_at_10"]) for row in query_rows)
                for query_rows in per_query.values()
            ),
            "mean_tie_aware_recall_at_10": statistics.fmean(
                statistics.fmean(float(row["tie_aware_recall_at_10"]) for row in query_rows)
                for query_rows in per_query.values()
            ),
            "returned_k_rate": sum(bool(row["returned_k"]) for row in condition_rows)
            / len(condition_rows),
        }
    return conditions


def load_verified_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve(strict=True)
    if not (run_dir / "COMPLETE.json").is_file():
        raise ValueError(f"run is not complete: {run_dir}")
    if (run_dir / "ACTIVE").exists() or (run_dir / "INVALID.json").exists():
        raise ValueError(f"run has an active or invalid marker: {run_dir}")
    # Verify the full payload before reading any measurements.
    verify_checksum_manifest(run_dir)
    terminal = read_json(run_dir / "COMPLETE.json")
    report = read_json(run_dir / "validation_report.json")
    config = read_json(run_dir / "config.json")
    stage = config["stage"]
    if terminal.get("valid") is not True or report.get("passed") is not True:
        raise ValueError(f"source run did not pass its validation gates: {run_dir}")
    if terminal.get("qualification_only") is not True:
        raise ValueError("this figure script accepts qualification runs only")
    scale = int(stage["scale_rows"])
    if scale not in (10_000, 100_000):
        raise ValueError("only 10k preflight and 100k qualification evidence is supported")
    rows = [
        json.loads(line)
        for line in (run_dir / "executions.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if len(rows) != int(stage["expected_timed_executions"]):
        raise ValueError("source execution count does not match its profile")
    if any(row["run_id"] != run_dir.name or int(row["scale_rows"]) != scale for row in rows):
        raise ValueError("execution provenance disagrees with the source directory")
    conditions = recompute_conditions(rows)
    saved_rows = read_json(run_dir / "summary.json")
    saved = {(str(row["method"]), int(row["filter_threshold"])): row for row in saved_rows}
    if len(saved_rows) != len(saved) or set(saved) != set(conditions):
        raise ValueError("stored condition summary is incomplete or duplicated")
    for key, recomputed in conditions.items():
        for field, value in recomputed.items():
            if not math.isclose(float(saved[key][field]), float(value), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"recomputed {field} differs from the summary for {key}")
    return {
        "path": run_dir,
        "run_id": run_dir.name,
        "scale_rows": scale,
        "stage_id": stage["stage_id"],
        "timed_query_count": int(stage["timed_query_count"]),
        "repetitions": int(stage["repetitions"]),
        "conditions": conditions,
        "source_sha256": {
            name: sha256_file(run_dir / name)
            for name in (
                "checksums.sha256", "COMPLETE.json", "config.json", "executions.jsonl",
                "summary.json", "validation_report.json",
            )
        },
    }


def measurement_markdown(runs: list[dict[str, Any]]) -> str:
    lines = [
        "# Verified qualification measurements",
        "",
        "Infrastructure-validation results only; these are not final research findings.",
        "Latency is client-observed prepared-query execute-and-fetch time, reduced to a",
        "median per query before taking the condition median. Recall is averaged per",
        "query before the condition mean. Repetitions are not independent query samples.",
        "Completeness is the fraction of executions returning exactly 10 qualifying rows.",
        "The filter metadata is synthetic and independent of SIFT vector content.",
        "",
        "| Scale | Method | Match rate | Queries | Repetitions | Median ms | Canonical Recall@10 | Tie-aware Recall@10 | Returning 10 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run in runs:
        for method, label in zip(METHODS, METHOD_LABELS, strict=True):
            for threshold in THRESHOLDS:
                row = run["conditions"][(method, threshold)]
                lines.append(
                    f"| {run['scale_rows']:,} | {label} | {threshold}% | "
                    f"{run['timed_query_count']} | {run['repetitions']} | "
                    f"{row['median_latency_ns'] / 1e6:.3f} | "
                    f"{row['mean_canonical_recall_at_10']:.3f} | "
                    f"{row['mean_tie_aware_recall_at_10']:.3f} | "
                    f"{row['returned_k_rate']:.1%} |"
                )
    lines += ["", "Source runs (all payload checksums verified before plotting):", ""]
    for run in runs:
        lines.append(f"- `{run['run_id']}` — `{run['path']}`")
    lines += [
        "",
        "The figures are descriptive grouped bars, with no smoothing, significance",
        "tests, or claims about larger scales. The panels use different qualification",
        "query/repetition counts where specified and must not be interpreted as a",
        "controlled full-scale comparison.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path, help="explicit completed qualification directories")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= len(args.run_dirs) <= 2:
        parser.error("provide one or two completed qualification run directories")
    runs = sorted((load_verified_run(path) for path in args.run_dirs), key=lambda run: run["scale_rows"])
    if len({run["scale_rows"] for run in runs}) != len(runs):
        parser.error("provide at most one run per scale")
    output_dir = args.output_dir.resolve()
    if any(output_dir == run["path"] or run["path"] in output_dir.parents for run in runs):
        parser.error("derived evidence must be outside immutable source runs")
    names = [item[0] for item in FIGURES] + ["VERIFIED_MEASUREMENTS.md", "figure_provenance.json"]
    existing = [name for name in names if (output_dir / name).exists()]
    if existing:
        parser.error(f"refusing to overwrite derived evidence: {existing}")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        parser.error(f"matplotlib is required in the active Python environment: {error}")

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 11,
        "axes.labelsize": 10, "axes.spines.top": False, "axes.spines.right": False,
    })
    payloads: dict[str, bytes] = {}
    for filename, metric, title, ylabel in FIGURES:
        figure, axes = plt.subplots(1, len(runs), figsize=(7.1 * len(runs), 5.4), squeeze=False, sharey=True)
        for axis, run in zip(axes[0], runs, strict=True):
            for offset, (method, label, color) in enumerate(zip(METHODS, METHOD_LABELS, COLORS, strict=True)):
                values = [float(run["conditions"][(method, threshold)][metric]) for threshold in THRESHOLDS]
                if metric == "median_latency_ns":
                    values = [value / 1e6 for value in values]
                axis.bar([index + (offset - 1) * 0.25 for index in range(5)], values,
                         width=0.24, color=color, label=label)
            axis.set_xticks(range(5), [f"{threshold}%" for threshold in THRESHOLDS])
            axis.set_xlabel("Qualifying fraction of loaded rows")
            axis.set_title(f"{run['scale_rows']:,} rows · {run['timed_query_count']} queries × {run['repetitions']} repetitions")
            axis.set_axisbelow(True)
            axis.grid(axis="y", alpha=0.22)
            if metric != "median_latency_ns":
                axis.set_ylim(0, 1.06)
            else:
                axis.set_ylim(bottom=0)
        axes[0][0].set_ylabel(ylabel)
        figure.suptitle(f"{title}\nQualification / infrastructure validation", fontsize=15, y=0.97)
        handles, labels = axes[0][0].get_legend_handles_labels()
        figure.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.055), ncol=3, frameon=False)
        figure.text(0.5, 0.025, "SIFT vectors · synthetic metadata · k=10 · descriptive measurements, no final research conclusions",
                    ha="center", fontsize=9)
        figure.subplots_adjust(top=0.78, bottom=0.24, left=0.095 if len(runs) == 1 else 0.06, right=0.98, wspace=0.15)
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=180, metadata={"Software": f"matplotlib {matplotlib.__version__}"})
        plt.close(figure)
        payloads[filename] = buffer.getvalue()
    payloads["VERIFIED_MEASUREMENTS.md"] = measurement_markdown(runs).encode("utf-8")
    provenance = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": str(Path(__file__).resolve()),
        "generator_sha256": sha256_file(Path(__file__)),
        "python_version": platform.python_version(),
        "matplotlib_version": matplotlib.__version__,
        "arguments": sys.argv[1:],
        "qualification_only": True,
        "final_research_conclusions": False,
        "source_payload_checksums_verified": True,
        "summaries_recomputed_from_executions": True,
        "latency_reduction": "median across repetitions per query, then median across queries",
        "recall_reduction": "mean across repetitions per query, then mean across queries",
        "completeness_reduction": "fraction of executions returning exactly 10 qualifying rows",
        "sources": [{key: str(value) if isinstance(value, Path) else value
                     for key, value in run.items() if key != "conditions"} for run in runs],
        "derived_artifact_sha256": {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()},
    }
    payloads["figure_provenance.json"] = (json.dumps(provenance, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        with (output_dir / name).open("xb") as handle:
            handle.write(payload)
    for run in runs:
        verify_checksum_manifest(run["path"])
    print(f"Created {len(payloads)} derived evidence files in {output_dir}")


if __name__ == "__main__":
    main()
