#!/usr/bin/env python3
"""One-off quality-only checkpoint; do not run during database measurement.

This file does not change the pinned experiment/analysis implementation. The
audited analyzer performs fresh offline verification and arithmetic in memory;
an explicit whitelist excludes its timing results from every published file.
The host power/sleep evidence must already have been saved before execution.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import metadata_association as audited

RUN_IDS = (
    "20261006T175652Z_5367e3fe7857",
    "20261006T180734Z_dcf7ada71ed5",
)
DEFAULT_OUTPUT = ROOT / "outputs/association_20261006/quality_checkpoint"
IDENTITY = ("stage_index", "scale_rows", "build_number", "run_id")
QUALITY = ("canonical_recall_at_10", "tie_aware_recall_at_10", "returned_k", "returned_count")
CONDITION_FIELDS = (
    *IDENTITY, "metadata_mode", "method", "filter_threshold", "query_count", "execution_count",
    "mean_canonical_recall_at_10", "mean_tie_aware_recall_at_10", "returned_k_rate", "mean_returned_count",
    "ordered_results_stable_query_count", "quality_stable_query_count",
)
PROOF_FIELDS = (
    "passed", "run_id", "source_commit", "config_sha256", "scale_rows", "build_number",
    "measured_executions", "preparation_executions", "ground_truth_records", "fresh_numpy_checks",
    "plan_audits", "physical_graph_builds", "metadata_modes_sharing_graph",
    "source_neighborhoods_recomputed", "association_gate_passed", "complete_payload_files",
    "input_checksums_unchanged", "source_distance_rows_checked", "independence_scope",
)
NOTICE = (
    "INCOMPLETE campaign: only the first two of four planned stages completed. "
    "There is one physical graph at 100k and one at 250k, not replicated graph evidence at either scale. "
    "Both stages' active-power query timing datasets are DISQUALIFIED and quarantined. "
    "Host logs report battery operation during both stages despite AC readings at run boundaries; "
    "stage 2 also contains host sleep intervals. No query latency or performance comparison is published here. "
    "Verified retrieval quality and source-exact density are retained as descriptive checkpoint evidence, "
    "not final findings or completion of the planned matched four-stage campaign."
)


def pick(record, fields):
    """Strict whitelist: future analyzer fields cannot silently enter outputs."""
    return {key: copy.deepcopy(record[key]) for key in fields}


def quality_only(report, host_evidence):
    """Project audited output to quality/density only, without recomputing metrics."""
    if (report["campaign_complete"] is not False or
            [(s["scale_rows"], s["build_number"]) for s in report["stages"]] != [(100000, 1), (250000, 1)] or
            [s["run_id"] for s in report["stages"]] != list(RUN_IDS) or
            len(report["conditions"]) != 60 or len(report["metadata_comparisons"]) != 30):
        raise ValueError("this checkpoint is exclusively the two verified first-build stages")
    stages = []
    for stage in report["stages"]:
        proof = stage["verification"]
        if proof["passed"] is not True:
            raise ValueError("independent verification must pass")
        stages.append({**pick(stage, IDENTITY),
            "source_commit": stage["source_commit"], "dataset_sha256": stage["dataset_sha256"],
            "queries": copy.deepcopy(stage["queries"]), "metadata": copy.deepcopy(stage["metadata"]),
            "verification": {key: copy.deepcopy(proof[key]) for key in PROOF_FIELDS if key in proof}})
    conditions = []
    for condition in report["conditions"]:
        density = condition["density_quality"]
        quality_density = {
            "query_count": density["query_count"],
            "rank_association_interpretation": density["rank_association_interpretation"],
            "groups": [pick(g, ("top40_count_bin", "query_count", *(f"mean_{f}" for f in QUALITY)))
                       for g in density["groups"]],
            "spearman_rank_associations": {x: pick(density["spearman_rank_associations"][x], QUALITY)
                for x in ("top40_qualifying_count", "query_anchor_distance", "filtered_exact_kth_distance")},
            "query_records": [pick(q, ("query_id", "top40_qualifying_count", *QUALITY,
                                        "query_anchor_distance", "filtered_exact_kth_distance"))
                              for q in density["query_records"]],
        }
        conditions.append({**pick(condition, CONDITION_FIELDS), "density_quality": quality_density})
    contrasts = []
    for contrast in report["metadata_comparisons"]:
        contrasts.append({**pick(contrast, (*IDENTITY, "method", "filter_threshold", "query_count")),
            "paired_quality_deltas": pick(contrast["paired_quality_deltas"], QUALITY),
            "paired_query_records": [pick(q, ("query_id", *(f"radial_minus_legacy_{f}" for f in QUALITY)))
                                      for q in contrast["paired_query_records"]]})
    result = {
        "schema_version": 1, "kind": "incomplete_metadata_association_quality_checkpoint",
        "campaign_complete": False, "status": "2 of 4 planned stages; one graph per scale",
        "timing_use_disposition": "DISQUALIFIED for both stages; not published in this checkpoint",
        "interpretation": NOTICE,
        "limitations": [
            "Same fixed 200 queries and all five technical repetitions retained; 60000 calls are not independent samples.",
            "Synthetic fixed-anchor block-balanced metadata, one inherited assignment; not semantic labels.",
            "Modes share a graph within each stage; scale contrasts have different graphs and chronological confounding.",
            "No repeat graph at either scale; no completed counterbalanced four-stage campaign.",
            "Top-40 exact-neighbor counts proxy local density; they are not HNSW candidate sets or visit counts.",
            "Descriptive rank associations use average ranks and null for constant vectors; no significance tests.",
            "Quality and source-distance verification do not validate the disqualified active-power timing regime.",
        ],
        "counts": copy.deepcopy(report["counts"]), "stages": stages, "conditions": conditions,
        "metadata_quality_comparisons": contrasts,
        "local_density_diagnostics": copy.deepcopy(report["local_density_diagnostics"]),
        "host_evidence": copy.deepcopy(host_evidence),
        "provenance": {**copy.deepcopy(report["provenance"]),
            "checkpoint_generator": str(Path(__file__).resolve()),
            "checkpoint_generator_sha256": audited.sha256(__file__),
            "projection_policy": "Strict quality/density whitelists; no query timings, phase durations, or timing associations emitted.",
            "raw_artifacts_modified": False},
    }
    assert_no_timing_measurements(result)
    return result


def assert_no_timing_measurements(value, path="root"):
    """Guard numeric/comparison timing fields, allowing explicit quarantine text.

    Source provenance can legitimately contain filenames mentioning latency;
    those entries are cryptographic hashes, not published timing measurements.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"inputs", "sources", "source_file_sha256"}:
                continue
            lower = key.lower()
            if any(token in lower for token in ("duration", "elapsed_ns", "_ms", "latency", "first_over_later", "later_pass", "pass_median", "pass_raw", "engineering_20pct", "normalization_later")):
                raise ValueError(f"timing field would leak into quality checkpoint: {path}.{key}")
            assert_no_timing_measurements(child, f"{path}.{key}")
    elif isinstance(value, list):
        for item in value:
            assert_no_timing_measurements(item, path)


def markdown(report):
    lines = ["# Incomplete metadata-association campaign: quality-only checkpoint", "", NOTICE, "",
             "## Scope and verification", "",
             "Both raw stages and source data are freshly checked by the pinned offline verifier before this projection. "
             "Raw artifacts remain unchanged. Producer COMPLETE markers mean their recorded checks passed; they do not override "
             "the subsequent host-evidence timing disqualification. This output's COMPLETE marker authenticates only this "
             "quality-only checkpoint, not completion of the four-stage research campaign.", "",
             f"Host-evidence record: `{report['host_evidence']['path']}`; SHA-256 `{report['host_evidence']['sha256']}`.", "",
             "Quality averages retain all five repetitions. Paired differences first average each query's five quality "
             "observations and then compare radial minus baseline on the same graph. Conditions and stages are not pooled.", "",
             "## Verified condition quality", "",
             "| Stage / scale / build | Metadata | Method | Filter | Canonical Recall@10 | Tie-aware Recall@10 | Returned 10 | Mean returned count | Stable quality queries |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for c in report["conditions"]:
        lines.append(f"| {c['stage_index']} / {c['scale_rows']} / {c['build_number']} | {c['metadata_mode']} | {c['method']} | {c['filter_threshold']}% | {c['mean_canonical_recall_at_10']:.4f} | {c['mean_tie_aware_recall_at_10']:.4f} | {c['returned_k_rate']:.1%} | {c['mean_returned_count']:.3f} | {c['quality_stable_query_count']}/200 |")
    lines += ["", "## Paired quality contrasts", "",
              "| Stage | Method | Filter | Canonical recall delta | Tie-aware recall delta | Returned-10 rate delta | Mean returned-count delta |",
              "|---:|---|---:|---:|---:|---:|---:|"]
    for c in report["metadata_quality_comparisons"]:
        d = c["paired_quality_deltas"]
        lines.append(f"| {c['stage_index']} | {c['method']} | {c['filter_threshold']}% | {d['canonical_recall_at_10']['mean']:+.4f} | {d['tie_aware_recall_at_10']['mean']:+.4f} | {d['returned_k']['mean']:+.4f} | {d['returned_count']['mean']:+.3f} |")
    lines += ["", "## Source-exact local association", "",
              "At L=100, D is the mean squared difference between query-local and global qualifying fractions. "
              "The prespecified manipulation gate applies to 50% and 5%. The permutation p95 is an engineering reference, "
              "not a population significance test. All filters are retained.", "",
              "| Stage | Filter | Baseline D | Radial D | Permutation p95 D | Condition passes |",
              "|---:|---:|---:|---:|---:|---|"]
    for stage in report["local_density_diagnostics"]:
        for threshold in audited.FILTERS:
            c = stage["diagnostics"]["primary_by_filter"][str(threshold)]
            lines.append(f"| {stage['stage_index']} | {threshold}% | {c['legacy_D']:.6g} | {c['radial_D']:.6g} | {c['permutation_D_p95_linear']:.6g} | {c['passes']} |")
    lines += ["", "JSON retains measured and disjoint-warmup density summaries, 60 quality conditions, "
              "30 paired quality contrasts, per-query quality-only contrasts, top-40 density groups (0, 1–9, 10+), "
              "rank associations with quality only, query-anchor distances and exact filtered kth distances. "
              "No query timing values or timing comparisons are included.", "", "## Limitations and next checkpoint", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    lines += ["", "Do not resume database experiments until host power and sleep handling are confirmed. "
              "Any timing replacement or campaign continuation must preserve these quarantined originals and explicitly "
              "document its relationship to the frozen protocol. No 500k/1M execution or final research conclusion is authorized here.", ""]
    return "\n".join(lines)


def figures(report, output):
    """Exactly two static figures: density and retrieval quality, never timing."""
    with tempfile.TemporaryDirectory(prefix="quality-checkpoint-matplotlib-") as cache:
        previous = os.environ.get("MPLCONFIGDIR")
        os.environ["MPLCONFIGDIR"] = cache
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            filters = sorted(audited.FILTERS)
            fig, axes = plt.subplots(1, 2, figsize=(10, 4.7), sharey=True)
            for ax, stage in zip(axes, report["local_density_diagnostics"], strict=True):
                summaries = stage["diagnostics"]["groups"]["measured"]["summary"]
                for mode, color, offset in (("legacy", "#2166ac", -.12), ("radial", "#b2182b", .12)):
                    cells = [summaries[mode][str(t)]["100"] for t in filters]
                    x = [i+offset for i in range(5)]
                    quantiles = [c["local_fraction_quantiles_linear"] for c in cells]
                    ax.vlines(x, [q["0.05"] for q in quantiles], [q["0.95"] for q in quantiles],
                              color=color, linewidth=3, alpha=.6)
                    ax.scatter(x, [q["0.5"] for q in quantiles], color=color, label=mode, zorder=3)
                ax.scatter(range(5), [t/100 for t in filters], marker="x", color="black", label="global fraction")
                ax.set_xticks(range(5), [f"{t}%" for t in filters]); ax.set_xlabel("Global selectivity")
                ax.set_title(f"Stage {stage['stage_index']}: {stage['scale_rows']//1000}k / one graph")
                ax.grid(axis="y", alpha=.2)
            axes[0].set_ylabel("Exact top-100 local qualifying fraction")
            axes[-1].legend(fontsize=8)
            fig.suptitle("Source-exact density: median and 5th–95th query percentiles\nIncomplete 2/4-stage campaign; 200 fixed queries; not confidence intervals", fontsize=11)
            fig.tight_layout(rect=(0, 0, 1, .87))
            fig.savefig(output / "local_density.png", dpi=160); plt.close(fig)
            fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True, sharey=True)
            index = {(c["stage_index"], c["metadata_mode"], c["method"], c["filter_threshold"]): c
                     for c in report["conditions"]}
            colors = {"exact": "#333333", "hnsw_standard": "#2166ac", "hnsw_iterative": "#b2182b"}
            for column, stage in enumerate(report["stages"]):
                for r, field in enumerate(("mean_canonical_recall_at_10", "returned_k_rate")):
                    ax = axes[r, column]
                    for method in audited.METHODS:
                        for mode, style, marker in (("legacy", "--", "o"), ("radial", "-", "s")):
                            values = [index[stage["stage_index"], mode, method, t][field] for t in filters]
                            ax.plot(range(5), values, color=colors[method], linestyle=style, marker=marker,
                                    label=f"{method.replace('hnsw_', '')}: {mode}", markersize=4)
                    ax.set_ylim(-.025, 1.025); ax.set_xticks(range(5), [f"{t}%" for t in filters]); ax.grid(alpha=.2)
                    if r == 0:
                        ax.set_title(f"Stage {stage['stage_index']}: {stage['scale_rows']//1000}k / one graph")
                    else:
                        ax.set_xlabel("Global selectivity")
            axes[0, 0].set_ylabel("Mean canonical Recall@10")
            axes[1, 0].set_ylabel("Returned-10 fraction")
            handles, labels = axes[0, 0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=9)
            fig.suptitle("Verified retrieval quality only — timing DISQUALIFIED\nOne graph per scale; 2/4 stages; paired metadata modes, not final findings", fontsize=12)
            fig.tight_layout(rect=(0, .1, 1, .91))
            fig.savefig(output / "retrieval_quality.png", dpi=160); plt.close(fig)
            return {"matplotlib": matplotlib.__version__}
        finally:
            if previous is None:
                os.environ.pop("MPLCONFIGDIR", None)
            else:
                os.environ["MPLCONFIGDIR"] = previous


def generate(host_evidence_path, output=DEFAULT_OUTPUT):
    host_path, output = Path(host_evidence_path).resolve(), Path(output).resolve()
    if not host_path.is_file():
        raise ValueError("save the host power/sleep evidence before running this generator")
    if output.exists():
        raise FileExistsError(f"refusing existing output: {output}")
    paths = [ROOT / "raw_results/association" / run_id for run_id in RUN_IDS]
    if "raw_results" in output.parts or any(p == output or p in output.parents for p in paths):
        raise ValueError("output must be separate from immutable raw inputs")
    host_review = audited.read_json(host_path)
    if set(host_review.get("timing_disqualified_run_ids", [])) != set(RUN_IDS):
        raise ValueError("host review must explicitly disqualify both checkpoint runs")
    host_evidence = {"path": str(host_path), "sha256": audited.sha256(host_path)}
    complete_report = audited.analyze(paths, allow_disqualified_for_quality_only=True)
    report = quality_only(complete_report, host_evidence)
    output.mkdir(parents=True, exist_ok=False)
    # Failure leaves a partial output without COMPLETE; no output is overwritten.
    report["figure_dependencies"] = figures(report, output)
    assert_no_timing_measurements(report)
    with (output / "QUALITY_CHECKPOINT.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False); handle.write("\n")
    with (output / "QUALITY_CHECKPOINT.md").open("x", encoding="utf-8") as handle:
        handle.write(markdown(report))
    audited.verify_inputs(complete_report)
    if audited.sha256(host_path) != host_evidence["sha256"]:
        raise ValueError("host evidence changed during quality checkpoint generation")
    if sorted(p.name for p in output.glob("*.png")) != ["local_density.png", "retrieval_quality.png"]:
        raise ValueError("quality checkpoint must contain exactly two declared figures")
    with (output / "checksums.sha256").open("x", encoding="utf-8") as handle:
        for path in sorted(output.iterdir()):
            if path.name != "checksums.sha256":
                handle.write(f"{audited.sha256(path)}  {path.name}\n")
    with (output / "COMPLETE.json").open("x", encoding="utf-8") as handle:
        json.dump({"schema_version": 1, "success": True, "artifact_type": report["kind"],
                   "campaign_complete": False, "completed_stages": 2, "planned_stages": 4,
                   "timing_use_disposition": "DISQUALIFIED for both stages",
                   "checksums_sha256": audited.sha256(output / "checksums.sha256")}, handle, sort_keys=True)
        handle.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-evidence", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    generate(args.host_evidence, args.output)
    print(args.output.resolve())
