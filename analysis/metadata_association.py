"""Read-only, descriptive analysis of the frozen matched metadata campaign.

Run only after database measurement has stopped. Every input stage is passed
through the independent offline verifier; input/source checksums are checked
again after analysis. Partial ordered campaign prefixes are explicitly labeled.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics as stats
import subprocess
import sys
import tempfile

from analysis.preparation_policy import (
    group_measured, percentile, query_ids, read_json, read_rows, sha256,
    snapshot, summarize_condition,
)
from experiments.association.protocol import FILTERS, METHODS, MODES, ROOT, STAGES, validate_config
from experiments.association.verify import verify_run

CAUTION = (
    "Descriptive matched-system evidence, not final research conclusions. Metadata modes "
    "share a physical graph within each stage; all five technical repetitions are retained. "
    "Queries, filters, repeated calls and nested scales are dependent. Graph builds and "
    "scales are shown separately, never pooled as independent observations. Residual host, "
    "order and cache effects remain; no steady-state or causal graph-traversal claim is made. "
    "Exact top-40 counts are a density proxy, not the HNSW candidate set."
)
QUALITY_FIELDS = ("canonical_recall_at_10", "tie_aware_recall_at_10", "returned_k", "returned_count")


def average_ranks(values):
    """One-based ranks with the arithmetic mean of tied positions."""
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("ranks require finite numeric values")
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks, start = [0.0] * len(values), 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for i in order[start:end]:
            ranks[i] = rank
        start = end
    return ranks


def spearman(x, y):
    """Descriptive Pearson correlation of average ranks; undefined -> None."""
    if len(x) != len(y):
        raise ValueError("paired rank association requires equal lengths")
    a, b = average_ranks(x), average_ranks(y)
    if len(a) < 2:
        return None
    ma, mb = stats.fmean(a), stats.fmean(b)
    da, db = [v - ma for v in a], [v - mb for v in b]
    norm = math.sqrt(sum(v*v for v in da) * sum(v*v for v in db))
    if norm == 0:
        return None
    return max(-1.0, min(1.0, sum(u*v for u, v in zip(da, db, strict=True)) / norm))


def query_summary(cell):
    if set(cell) != set(range(1, 6)):
        raise ValueError("each paired query requires five repetitions")
    return {"query_median_ms": stats.median(cell[r]["duration_ns"] for r in range(1, 6)) / 1e6,
            **{field: stats.fmean(cell[r][field] for r in range(1, 6)) for field in QUALITY_FIELDS}}


def compare_modes(legacy, radial):
    """Pair by query before differences/ratios; quality averages retain all passes."""
    if not legacy or set(legacy) != set(radial):
        raise ValueError("metadata contrasts require identical nonempty query cells")
    records = []
    for query in sorted(legacy):
        left, right = query_summary(legacy[query]), query_summary(radial[query])
        if left["query_median_ms"] <= 0 or right["query_median_ms"] <= 0:
            raise ValueError("paired latency requires positive query medians")
        records.append({"query_id": query,
            "radial_over_legacy_query_median_latency": right["query_median_ms"] / left["query_median_ms"],
            **{f"radial_minus_legacy_{field}": right[field] - left[field] for field in QUALITY_FIELDS}})
    ratios = [r["radial_over_legacy_query_median_latency"] for r in records]
    return {"query_count": len(records),
            "median_paired_radial_over_legacy_query_median_latency": stats.median(ratios),
            "p95_paired_radial_over_legacy_query_median_latency": percentile(ratios),
            "paired_quality_deltas": {field: {
                "mean": stats.fmean(r[f"radial_minus_legacy_{field}"] for r in records),
                "median": stats.median(r[f"radial_minus_legacy_{field}"] for r in records),
                "positive_query_count": sum(r[f"radial_minus_legacy_{field}"] > 0 for r in records),
                "zero_query_count": sum(r[f"radial_minus_legacy_{field}"] == 0 for r in records),
                "negative_query_count": sum(r[f"radial_minus_legacy_{field}"] < 0 for r in records),
            } for field in QUALITY_FIELDS}, "paired_query_records": records}


def density_quality(queries, neighbors, truth, mode, threshold):
    """Per-query descriptive relationships; do not repeat density five times."""
    if mode not in MODES or threshold not in FILTERS:
        raise ValueError("unknown density condition")
    records = []
    for query in sorted(queries):
        n = neighbors[query]
        count = n["local_counts"][mode][str(threshold)]["40"]
        if type(count) is not int or not 0 <= count <= 40:
            raise ValueError("invalid top-40 qualifying count")
        descriptors = {"query_anchor_distance": n["query_anchor_distance"],
                       "filtered_exact_kth_distance": truth[query, threshold]["boundary_distance"]}
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in descriptors.values()):
            raise ValueError("invalid query difficulty descriptor")
        records.append({"query_id": query, "top40_qualifying_count": count,
                        **query_summary(queries[query]), **descriptors})
    groups = []
    for label, minimum, maximum in (("0", 0, 0), ("1..9", 1, 9), ("10+", 10, 40)):
        cells = [r for r in records if minimum <= r["top40_qualifying_count"] <= maximum]
        groups.append({"top40_count_bin": label, "query_count": len(cells),
                       **{f"mean_{field}": stats.fmean(r[field] for r in cells) if cells else None
                          for field in QUALITY_FIELDS},
                       "median_query_median_ms": stats.median(r["query_median_ms"] for r in cells) if cells else None})
    relations = {}
    for x in ("top40_qualifying_count", "query_anchor_distance", "filtered_exact_kth_distance"):
        relations[x] = {y: spearman([r[x] for r in records], [r[y] for r in records])
                        for y in (*QUALITY_FIELDS, "query_median_ms")}
    return {"query_count": len(records), "groups": groups, "spearman_rank_associations": relations,
            "rank_association_interpretation": "Descriptive only; average ranks for ties; null means fewer than two observations or a constant rank vector; no p-values.",
            "query_records": records}


def check_campaign_contract(stages):
    """Same selection/metadata across builds; inherited labels across scales."""
    if not 1 <= len(stages) <= len(STAGES):
        raise ValueError("require one to four completed stages")
    observed = [(s["scale_rows"], s["build_number"]) for s in stages]
    if observed != list(STAGES[:len(stages)]):
        raise ValueError("inputs must be an ordered prefix of the frozen campaign")
    first = stages[0]
    for current in stages:
        for field in ("queries", "dataset_sha256", "source_file_sha256"):
            if current[field] != first[field]:
                raise ValueError(f"campaign changed {field}")
        meta = current["metadata"]
        reference = first["metadata"]
        if meta["prefix_100k_ordered_base_ids_int64_le_sha256"] != reference["ordered_base_ids_int64_le_sha256"]:
            raise ValueError("100k ID prefix inheritance failed")
        if meta["prefix_100k_radial_labels_int16_le_sha256"] != reference["radial_labels_int16_le_sha256"]:
            raise ValueError("100k radial label inheritance failed")
        if meta["anchor_float64_le_sha256"] != reference["anchor_float64_le_sha256"]:
            raise ValueError("fixed anchor changed")
        for earlier in stages:
            if current["scale_rows"] == earlier["scale_rows"] and current["metadata"] != earlier["metadata"]:
                raise ValueError("metadata differs between builds at the same scale")
    return len(stages) == len(STAGES)


def provenance(inputs, sources):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    helper = Path(sys.modules[snapshot.__module__].__file__).resolve()
    return {"generator": str(Path(__file__).resolve()), "generator_sha256": sha256(__file__),
            "audited_summary_helper": str(helper), "audited_summary_helper_sha256": sha256(helper),
            "repository_head": git("rev-parse", "HEAD"),
            "git_status_porcelain": git("status", "--porcelain=v1").splitlines(),
            "python_version": sys.version, "inputs": inputs, "sources": sources}


def verify_inputs(report):
    for item in report["provenance"]["inputs"]:
        if snapshot(item["path"]) != item["sha256"]:
            raise ValueError("raw artifacts changed during analysis")
    for source in report["provenance"]["sources"]:
        if sha256(source["path"]) != source["sha256"]:
            raise ValueError("source dataset changed during analysis")


def analyze(paths):
    paths = [Path(p).resolve() for p in paths]
    if not 1 <= len(paths) <= 4 or len(set(paths)) != len(paths):
        raise ValueError("require one to four distinct input stages")
    inputs = [{"path": str(p), "sha256": snapshot(p)} for p in paths]
    sources, stages, conditions, comparisons, densities = {}, [], [], [], []
    for index, path in enumerate(paths, 1):
        config = read_json(path / "config.json")
        validate_config(config)
        if (config["scale_rows"], config["build_number"]) != STAGES[index - 1]:
            raise ValueError("stage order is not the frozen campaign prefix")
        proof = verify_run(path)
        if proof.get("passed") is not True or proof.get("run_id") != path.name:
            raise ValueError("independent verification did not pass for this stage")
        measured, warmup = query_ids(read_json(path / "queries.json"))
        dataset, manifest = read_json(path / "dataset_manifest.json"), read_json(path / "manifest.json")
        source = Path(dataset["path"]).resolve()
        source_hash = sha256(source)
        if source_hash != dataset["sha256"]:
            raise ValueError("source checksum differs from input manifest")
        sources[str(source)] = {"path": str(source), "sha256": source_hash}
        identity = {"stage_index": index, "scale_rows": config["scale_rows"],
                    "build_number": config["build_number"], "run_id": path.name}
        stage = {**identity, "queries": {"measured": measured, "warmup": warmup},
                 "dataset_sha256": source_hash, "source_file_sha256": manifest["source_file_sha256"],
                 "source_commit": manifest["git_at_start"]["commit"],
                 "metadata": read_json(path / "metadata_manifest.json"), "verification": proof,
                 "phase_metrics": read_json(path / "phase_metrics.json"),
                 "relation_sizes": read_json(path / "database_evidence.json")["relation_sizes"],
                 "elapsed_ns": read_json(path / "validation_report.json")["elapsed_ns"]}
        stages.append(stage)
        rows = read_rows(path / "executions.jsonl")
        if any(r["run_id"] != path.name or r["scale_rows"] != config["scale_rows"] or
               r["build_number"] != config["build_number"] or r["phase"] != "measured" for r in rows):
            raise ValueError("measured execution identity differs")
        keys = {(mode, method, threshold) for mode in MODES for method in METHODS for threshold in FILTERS}
        groups = group_measured(rows, lambda r: (r["metadata_mode"], r["method"], r["filter_threshold"]), keys, measured)
        neighbors_list = read_rows(path / "neighbors.jsonl")
        neighbors = {r["query_id"]: r for r in neighbors_list}
        if len(neighbors) != len(neighbors_list) or set(neighbors) != set(measured + warmup):
            raise ValueError("neighborhood query coverage differs")
        diagnostic = read_json(path / "association_diagnostics.json")
        if diagnostic.get("gate_passed") is not True:
            raise ValueError("manipulation check did not pass")
        densities.append({**identity, "diagnostics": diagnostic})
        for mode in MODES:
            truth_rows = read_rows(path / f"{mode}_ground_truth.jsonl")
            truth = {(r["query_id"], r["filter_threshold"]): r for r in truth_rows}
            if len(truth_rows) != 1000 or set(truth) != {(q, t) for q in measured for t in FILTERS}:
                raise ValueError("filtered ground-truth grid differs")
            for method in METHODS:
                for threshold in FILTERS:
                    cells = groups[mode, method, threshold]
                    summary = summarize_condition(cells)
                    if method == "exact" and any(summary[f] != 1 for f in (
                        "mean_canonical_recall_at_10", "mean_tie_aware_recall_at_10", "returned_k_rate")):
                        raise ValueError("exact quality baseline is not complete ground truth")
                    conditions.append({**identity, "metadata_mode": mode, "method": method,
                        "filter_threshold": threshold, **summary,
                        "density_quality": density_quality(cells, neighbors, truth, mode, threshold)})
        for method in METHODS:
            for threshold in FILTERS:
                comparisons.append({**identity, "method": method, "filter_threshold": threshold,
                    **compare_modes(groups["legacy", method, threshold], groups["radial", method, threshold])})
    complete = check_campaign_contract(stages)
    report = {"schema_version": 1, "kind": "metadata_association_descriptive",
              "campaign_complete": complete, "status": "complete four-stage campaign" if complete else "partial ordered campaign prefix",
              "interpretation": CAUTION, "stages": stages, "conditions": conditions,
              "metadata_comparisons": comparisons, "local_density_diagnostics": densities,
              "counts": {"completed_stages": len(stages), "planned_stages": 4,
                         "measured_executions": len(stages)*30000, "warmup_executions": len(stages)*600,
                         "query_ids_per_condition": 200, "condition_count": len(conditions)},
              "provenance": provenance(inputs, list(sources.values()))}
    verify_inputs(report)
    return report


def markdown(report):
    lines = ["# Matched metadata association: descriptive results", "", report["interpretation"], "",
             f"Status: **{report['status']}**. Completed stages: {len(report['stages'])}/4. "
             "A COMPLETE marker authenticates this analysis output; it does not imply all four stages ran.", "",
             "Latency p50/p95 are across 200 per-query medians of all five repetitions, not pooled requests. "
             "Pass medians and pass raw-request p95 are separate diagnostics. Quality averages retain all repetitions; "
             "rank associations use one mean-quality/median-latency observation per query. "
             "Synthetic block-balanced radial metadata is not semantic labeling or established independence.", "",
             "## Condition measurements (stages remain separate)", "",
             "| Stage / scale / build | Metadata | Method | Filter | Query-median p50 / p95 ms | Recall canonical / tie-aware | Returned 10 | Mean count | Five pass medians ms | Five raw-request p95 ms | First/later ratio | Later max/min |",
             "|---|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|"]
    for c in report["conditions"]:
        passes = lambda field: ", ".join(f"{v:.3f}" for v in c[field])
        lines.append(f"| {c['stage_index']} / {c['scale_rows']} / {c['build_number']} | {c['metadata_mode']} | {c['method']} | {c['filter_threshold']}% | {c['all_five_median_query_median_ms']:.3f} / {c['all_five_p95_query_median_ms']:.3f} | {c['mean_canonical_recall_at_10']:.4f} / {c['mean_tie_aware_recall_at_10']:.4f} | {c['returned_k_rate']:.1%} | {c['mean_returned_count']:.3f} | {passes('pass_median_ms')} | {passes('pass_raw_request_p95_ms')} | {c['median_paired_first_over_later']:.3f} | {c['later_pass_max_over_min']:.3f} |")
    lines += ["", "## Paired radial-minus-baseline contrasts", "",
              "Latency is the median of 200 paired radial/baseline query-median ratios. Quality contrasts are means of query-paired differences, not independent samples.", "",
              "| Stage | Method | Filter | Paired latency ratio | Recall delta | Tie-aware delta | Returned-10 rate delta | Returned-count delta |",
              "|---:|---|---:|---:|---:|---:|---:|---:|"]
    for c in report["metadata_comparisons"]:
        delta = c["paired_quality_deltas"]
        lines.append(f"| {c['stage_index']} | {c['method']} | {c['filter_threshold']}% | {c['median_paired_radial_over_legacy_query_median_latency']:.3f} | {delta['canonical_recall_at_10']['mean']:+.4f} | {delta['tie_aware_recall_at_10']['mean']:+.4f} | {delta['returned_k']['mean']:+.4f} | {delta['returned_count']['mean']:+.3f} |")
    lines += ["", "## Local association and manipulation checks", "",
              "Primary neighborhood L=100. D is mean squared local-fraction deviation from global selectivity. "
              "The prespecified engineering gate applies to 50% and 5%; permutation p95 is a reference, not a population test.", "",
              "| Stage | Filter | Baseline D | Radial D | Permutation p95 D | Gate condition passed |",
              "|---:|---:|---:|---:|---:|---|"]
    for d in report["local_density_diagnostics"]:
        for threshold in FILTERS:
            c = d["diagnostics"]["primary_by_filter"][str(threshold)]
            lines.append(f"| {d['stage_index']} | {threshold}% | {c['legacy_D']:.6g} | {c['radial_D']:.6g} | {c['permutation_D_p95_linear']:.6g} | {c['passes']} |")
    lines += ["", "## Evidence and limitations", "",
              "analysis.json retains per-query paired contrasts, all top-40 density groups (0, 1–9, 10+), "
              "descriptive Spearman associations (null for constant vectors), exact filtered kth distances, "
              "query-anchor distances, measured and disjoint-warmup density summaries, "
              "timing-drift diagnostics, resource phase costs, physical sizes and independent verification proofs. "
              "One fixed anchor and one inherited synthetic metadata assignment do not establish broad generality. "
              "Exact uses work_mem=4MB and ANN=64MB; configured-system comparisons do not equalize memory. "
              "No confidence intervals, significance tests, adaptive selector, or larger-scale extrapolation is produced.", "",
              "All input artifact manifests and source data hashes are checked before and after analysis. "
              "The verifier reuses explicitly identified audited helpers; it is not an independently implemented database engine. "
              "Generator and dependency hashes, source commits and complete raw-artifact paths are in analysis.json.", ""]
    return "\n".join(lines)


def figures(report, output):
    """Three static scientific figures; synthetic fixtures used only in tests."""
    with tempfile.TemporaryDirectory(prefix="association-matplotlib-") as cache:
        previous = os.environ.get("MPLCONFIGDIR")
        os.environ["MPLCONFIGDIR"] = cache
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            stages, filters = report["stages"], sorted(FILTERS)
            labels = [f"S{s['stage_index']}: {s['scale_rows']//1000}k / build {s['build_number']}" for s in stages]
            fig, axes = plt.subplots(1, len(stages), figsize=(4.5*len(stages), 4.5), squeeze=False, sharey=True)
            for ax, stage, title in zip(axes[0], report["local_density_diagnostics"], labels, strict=True):
                summary = stage["diagnostics"]["groups"]["measured"]["summary"]
                for mode, color, offset in (("legacy", "#2166ac", -.12), ("radial", "#b2182b", .12)):
                    cells = [summary[mode][str(t)]["100"] for t in filters]
                    x = [i+offset for i in range(5)]
                    medians = [c["local_fraction_quantiles_linear"]["0.5"] for c in cells]
                    ax.vlines(x, [c["local_fraction_quantiles_linear"]["0.05"] for c in cells],
                              [c["local_fraction_quantiles_linear"]["0.95"] for c in cells], color=color, linewidth=3, alpha=.6)
                    ax.scatter(x, medians, color=color, label=mode, zorder=3)
                ax.scatter(range(5), [t/100 for t in filters], marker="x", color="black", label="global fraction")
                ax.set_xticks(range(5), [f"{t}%" for t in filters]); ax.set_title(title)
                ax.set_xlabel("Global filter selectivity"); ax.grid(axis="y", alpha=.2)
            axes[0][0].set_ylabel("Exact top-100 local qualifying fraction")
            axes[0][-1].legend(fontsize=8)
            fig.suptitle("Query-local qualifying density: median and 5th–95th query percentiles\n200 fixed measured queries per stage; descriptive, not confidence intervals", fontsize=11)
            fig.tight_layout(rect=(0, 0, 1, .88)); fig.savefig(output / "local_density.png", dpi=160); plt.close(fig)
            condition_keys = [(m, t) for m in METHODS for t in filters]
            comparison = {(c["stage_index"], c["method"], c["filter_threshold"]): c for c in report["metadata_comparisons"]}
            for name, quality in (("quality_contrast.png", True), ("paired_latency_ratio.png", False)):
                ncols = len(stages) if quality else 1
                fig, axes = plt.subplots(1, ncols, figsize=(max(8, 4.5*ncols), 8), squeeze=False, sharey=True)
                for si, (stage, title) in enumerate(zip(stages, labels, strict=True)):
                    ax = axes[0][si if quality else 0]
                    cells = [comparison[stage["stage_index"], m, t] for m, t in condition_keys]
                    if quality:
                        for field, label, offset, marker in (("canonical_recall_at_10", "Recall@10 delta", -.12, "o"),
                                                            ("returned_k", "Returned-10 rate delta", .12, "s")):
                            ax.scatter([c["paired_quality_deltas"][field]["mean"] for c in cells],
                                       [i+offset for i in range(15)], label=label, marker=marker)
                        ax.axvline(0, color="gray", linestyle="--"); ax.set_title(title)
                        ax.set_xlabel("Mean paired radial − baseline")
                    else:
                        ax.scatter([c["median_paired_radial_over_legacy_query_median_latency"] for c in cells],
                                   [i+(si-(len(stages)-1)/2)*.14 for i in range(15)], label=title, marker=("o", "s", "^", "D")[si])
                    ax.set_yticks(range(15), [f"{m.replace('hnsw_', '')} / {t}%" for m, t in condition_keys]); ax.grid(axis="x", alpha=.2)
                for ax in axes[0]:
                    ax.legend(fontsize=8)
                axes[0][0].invert_yaxis()
                if not quality:
                    axes[0][0].axvline(1, color="gray", linestyle="--"); axes[0][0].set_xscale("log")
                    axes[0][0].set_xlabel("Median paired radial/baseline query-median latency (log scale); <1 radial faster")
                fig.suptitle(("Metadata quality contrasts" if quality else "Metadata latency contrasts") +
                             "\nAll five repetitions; same graph within each stage; stages are not pooled", fontsize=12)
                fig.tight_layout(rect=(0, 0, 1, .92)); fig.savefig(output / name, dpi=160); plt.close(fig)
            return {"matplotlib": matplotlib.__version__}
        finally:
            if previous is None:
                os.environ.pop("MPLCONFIGDIR", None)
            else:
                os.environ["MPLCONFIGDIR"] = previous


def generate(paths, output):
    paths, output = [Path(p).resolve() for p in paths], Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing existing output: {output}")
    if "raw_results" in output.parts or any(p == output or p in output.parents for p in paths):
        raise ValueError("output must be outside raw results and input directories")
    report = analyze(paths)
    output.mkdir(parents=True, exist_ok=False)
    # Preserve incomplete output without COMPLETE if rendering/checking fails.
    report["figure_dependencies"] = figures(report, output)
    with (output / "analysis.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False); handle.write("\n")
    with (output / "ANALYSIS.md").open("x", encoding="utf-8") as handle:
        handle.write(markdown(report))
    verify_inputs(report)
    with (output / "checksums.sha256").open("x", encoding="utf-8") as handle:
        for path in sorted(output.iterdir()):
            if path.name != "checksums.sha256":
                handle.write(f"{sha256(path)}  {path.name}\n")
    with (output / "COMPLETE.json").open("x", encoding="utf-8") as handle:
        json.dump({"schema_version": 1, "success": True, "artifact_type": report["kind"],
                   "campaign_complete": report["campaign_complete"], "completed_stages": len(report["stages"]),
                   "checksums_sha256": sha256(output / "checksums.sha256")}, handle, sort_keys=True)
        handle.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    generate(args.paths, args.output)
    print(args.output.resolve())
