#!/usr/bin/env python3
"""Offline, descriptive analysis of historical runs and the preparation-policy pilot.

No database access. No observations are deleted. The five recorded repetitions
remain primary, including when preparation fails the engineering stability flag.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics as stats
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("exact", "hnsw_standard", "hnsw_iterative")
FILTERS = (1, 5, 10, 20, 50)
CONDITIONS = [(m, f) for m in METHODS for f in FILTERS]
CAUTION = (
    "Descriptive measurement-qualification evidence, not final research findings. "
    "All five repetitions are retained. The same 200 queries are reused; repeated "
    "executions, conditions, and the two graph builds are not pooled as independent "
    "samples. No inferential test, cache-causality claim, or proof of steady state "
    "is made. Historical and pilot campaigns are context, not a matched comparison."
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_rows(path):
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def snapshot(run):
    """Independent manifest/coverage check; terminal marker is hashed separately."""
    run = Path(run).resolve()
    if not run.is_dir() or (run / "ACTIVE").exists() or (run / "INVALID.json").exists():
        raise ValueError("require finalized successful input directory")
    paths = list(run.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("symlinks are not accepted in input artifacts")
    observed = {str(path.relative_to(run)): sha256(path)
                for path in sorted(paths) if path.is_file()}
    if not {"COMPLETE.json", "checksums.sha256"} <= observed.keys():
        raise ValueError("completion marker and checksums are required")
    expected = {}
    for line in (run / "checksums.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if name in expected or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid or duplicate manifest entry")
        expected[name] = digest
    if expected != {n: h for n, h in observed.items()
                    if n not in {"COMPLETE.json", "checksums.sha256"}}:
        raise ValueError("input checksum or manifest coverage mismatch")
    if read_json(run / "COMPLETE.json").get("valid") is not True:
        raise ValueError("input is not marked valid")
    return observed


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be integer >= {minimum}")
    return value


def percentile(values, fraction=.95):
    """Linear interpolation at (n-1)*fraction, independently implemented."""
    ordered = sorted(values)
    if not ordered or not 0 <= fraction <= 1:
        raise ValueError("percentile needs values and fraction in [0,1]")
    position = (len(ordered) - 1) * fraction
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def quality(row):
    return (tuple(row["result_ids"]), tuple(row["distances"]), row["canonical_recall_at_10"],
            row["tie_aware_recall_at_10"], row["returned_k"], row["returned_count"])


def validate_row(row, *, measured):
    integer(row["duration_ns"], "duration_ns", 1)
    integer(row["query_id"], "query_id")
    if row["method"] not in METHODS or type(row["filter_threshold"]) is not int or row["filter_threshold"] not in FILTERS:
        raise ValueError("unknown method/filter")
    if not {"error_type", "error_message", "timeout"} <= row.keys() or row["error_type"] is not None or row["error_message"] is not None or row["timeout"] is not False:
        raise ValueError("input execution errors are not accepted")
    ids = row["result_ids"]
    if not isinstance(ids, list) or len(ids) > 10 or len(ids) != len(set(ids)):
        raise ValueError("invalid result IDs")
    for identifier in ids:
        integer(identifier, "result ID")
    distances = row["distances"]
    if not isinstance(distances, list) or len(distances) != len(ids) or any(
        type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in distances
    ) or distances != sorted(distances):
        raise ValueError("invalid or unordered distances")
    if integer(row["returned_count"], "returned_count") != len(ids) or type(row["returned_k"]) is not bool or row["returned_k"] != (len(ids) == 10):
        raise ValueError("result completeness mismatch")
    if measured:
        integer(row["repetition"], "repetition", 1)
        for field in ("canonical_recall_at_10", "tie_aware_recall_at_10"):
            value = row[field]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("invalid recall")
        if row["canonical_recall_at_10"] > row["tie_aware_recall_at_10"] + 1e-12:
            raise ValueError("tie-aware recall lower than canonical")


def summarize_condition(queries):
    """Five-repetition cells for one graph, preparation arm, method and filter."""
    cells = [queries[q] for q in sorted(queries)]
    if not cells or any(set(cell) != set(range(1, 6)) for cell in cells):
        raise ValueError("each query must have all five repetitions")
    query_medians = [stats.median(cell[r]["duration_ns"] for r in range(1, 6)) for cell in cells]
    later_medians = [stats.median(cell[r]["duration_ns"] for r in range(2, 6)) for cell in cells]
    ratios = [cell[1]["duration_ns"] / later for cell, later in zip(cells, later_medians)]
    pass_values = [[cell[r]["duration_ns"] for cell in cells] for r in range(1, 6)]
    pass_medians = [stats.median(values) for values in pass_values]
    baseline = stats.median(later_medians)
    normalized = [value / baseline for value in pass_medians]
    ordered_stable = sum(len({tuple(cell[r]["result_ids"]) for r in range(1, 6)}) == 1 for cell in cells)
    quality_stable = sum(len({quality(cell[r]) for r in range(1, 6)}) == 1 for cell in cells)
    rows = [cell[r] for cell in cells for r in range(1, 6)]
    return {
        "query_count": len(cells), "execution_count": len(rows),
        "pass_median_ms": [n / 1e6 for n in pass_medians],
        "pass_raw_request_p95_ms": [percentile(values) / 1e6 for values in pass_values],
        "all_five_median_query_median_ms": stats.median(query_medians) / 1e6,
        "all_five_p95_query_median_ms": percentile(query_medians) / 1e6,
        "median_paired_first_over_later": stats.median(ratios),
        "median_abs_log2_first_over_later": stats.median(abs(math.log2(value)) for value in ratios),
        "later_pass_max_over_min": max(pass_medians[1:]) / min(pass_medians[1:]),
        "normalization_later_median_query_median_ms": baseline / 1e6,
        "all_pass_normalized_medians": normalized,
        "engineering_20pct_flag": any(value < .8 or value > 1.2 for value in normalized),
        "ordered_results_stable_query_count": ordered_stable,
        "quality_stable_query_count": quality_stable,
        "mean_canonical_recall_at_10": stats.fmean(row["canonical_recall_at_10"] for row in rows),
        "mean_tie_aware_recall_at_10": stats.fmean(row["tie_aware_recall_at_10"] for row in rows),
        "returned_k_rate": stats.fmean(row["returned_k"] for row in rows),
        "mean_returned_count": stats.fmean(row["returned_count"] for row in rows),
    }


def group_measured(rows, key_function, expected_keys, query_ids):
    groups = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        validate_row(row, measured=True)
        key = key_function(row)
        query, repetition = row["query_id"], row["repetition"]
        if key not in expected_keys or query not in query_ids or repetition not in range(1, 6):
            raise ValueError("execution outside declared grid")
        if repetition in groups[key][query]:
            raise ValueError("duplicate query/repetition")
        groups[key][query][repetition] = row
    if set(groups) != expected_keys or any(set(g) != set(query_ids) for g in groups.values()):
        raise ValueError("incomplete condition/query grid")
    for group in groups.values():
        if any(set(cell) != set(range(1, 6)) for cell in group.values()):
            raise ValueError("incomplete repetition grid")
    return groups


def query_ids(document):
    measured, warmup = document["measured_query_ids"], document["warmup_query_ids"]
    for values, count in ((measured, 200), (warmup, 20)):
        if len(values) != count or len(set(values)) != count:
            raise ValueError("expected 200 measured and 20 unique warmup queries")
        for value in values:
            integer(value, "query ID")
            if value >= 10000:
                raise ValueError("SIFT query ID out of range")
    if set(measured) & set(warmup):
        raise ValueError("warmup and measured queries overlap")
    return measured, warmup


def provenance(inputs, source=None):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    result = {
        "generator": str(Path(__file__).resolve()), "generator_sha256": sha256(__file__),
        "repository_head": git("rev-parse", "HEAD"),
        "git_status_porcelain": git("status", "--porcelain=v1").splitlines(),
        "python_version": sys.version, "inputs": inputs,
    }
    if source:
        result["source"] = {"path": str(Path(source).resolve()), "sha256": sha256(source)}
    return result


def verify_inputs(report):
    for record in report["provenance"]["inputs"]:
        if snapshot(record["path"]) != record["sha256"]:
            raise ValueError("input changed during analysis")
    source = report["provenance"].get("source")
    if source and sha256(source["path"]) != source["sha256"]:
        raise ValueError("source data changed during analysis")


def feature_descriptors(source, measured, warmup):
    import h5py
    import numpy as np
    result = {"interpretation": "Descriptive only; supplied full-1M unfiltered distances are query features, not filtered 100k ground truth.", "groups": {}}
    with h5py.File(source, "r") as handle:
        if handle["test"].shape != (10000, 128) or handle["distances"].shape != (10000, 100):
            raise ValueError("unexpected SIFT query or supplied-distance shape")
        for label, ids in (("measured", measured), ("warmup", warmup)):
            vectors = handle["test"][sorted(ids)].astype("float64")
            distances = handle["distances"][sorted(ids)].astype("float64")
            values = {"vector_l2_norm": np.linalg.norm(vectors, axis=1),
                      "zero_dimension_count": (vectors == 0).sum(axis=1),
                      "full1m_nearest_distance": distances[:, 0],
                      "full1m_10th_distance": distances[:, 9],
                      "full1m_100th_distance": distances[:, 99],
                      "full1m_d1_over_d10": distances[:, 0] / distances[:, 9]}
            result["groups"][label] = {"query_count": len(ids), "features": {
                key: {"min_q25_median_q75_max": np.quantile(value, [0, .25, .5, .75, 1]).tolist(),
                      "mean": float(value.mean())} for key, value in values.items()}}
    return result


def analyze_historical(run_paths, source=None):
    if len(run_paths) != 2 or len({str(Path(p).resolve()) for p in run_paths}) != 2:
        raise ValueError("two distinct historical runs required")
    inputs = [{"path": str(Path(p).resolve()), "sha256": snapshot(p)} for p in run_paths]
    report = {"schema_version": 1, "kind": "historical_reanalysis", "interpretation": CAUTION,
              "provenance": provenance(inputs, source), "conditions": []}
    selections, rounds = [], []
    for item in inputs:
        run = Path(item["path"])
        if source and read_json(run / "dataset_manifest.json")["sha256"] != report["provenance"]["source"]["sha256"]:
            raise ValueError("query-feature source differs from historical dataset checksum")
        config = read_json(run / "config.json")["stage"]
        round_number = config["experiment_round"]
        if type(round_number) is not int or round_number not in (1, 2) or any(config.get(key) != value for key, value in {
            "scale_rows": 100000, "timed_query_count": 200, "repetitions": 5,
            "campaign_id": "standalone-100k-v1", "expected_timed_executions": 15000,
        }.items()):
            raise ValueError("not the historical full-100k profile")
        measured, warmup = query_ids(read_json(run / "queries.json"))
        selections.append((measured, warmup)); rounds.append(round_number)
        rows = read_rows(run / "executions.jsonl")
        if any(row["run_id"] != run.name or row["round"] != round_number or row["scale_rows"] != 100000 for row in rows):
            raise ValueError("historical execution identity mismatch")
        groups = group_measured(rows, lambda r: (r["method"], r["filter_threshold"]), set(CONDITIONS), measured)
        for method, threshold in CONDITIONS:
            report["conditions"].append({"build_number": round_number, "run_id": run.name,
                "method": method, "filter_threshold": threshold,
                **summarize_condition(groups[(method, threshold)])})
    if sorted(rounds) != [1, 2] or selections[0] != selections[1]:
        raise ValueError("historical rounds or query selection differ")
    report["conditions"].sort(key=lambda c: (c["build_number"], METHODS.index(c["method"]), c["filter_threshold"]))
    report["prevalence"] = {
        "condition_count": 30,
        "paired_first_over_later_above_1_2": sum(c["median_paired_first_over_later"] > 1.2 for c in report["conditions"]),
        "paired_first_over_later_above_2": sum(c["median_paired_first_over_later"] > 2 for c in report["conditions"]),
        "later_pass_max_over_min_above_1_2": sum(c["later_pass_max_over_min"] > 1.2 for c in report["conditions"]),
        "engineering_20pct_flags": sum(c["engineering_20pct_flag"] for c in report["conditions"]),
        "threshold_interpretation": "Historical thresholds are exploratory descriptions, not retroactive acceptance tests.",
    }
    report["query_features"] = feature_descriptors(source, *selections[0]) if source else {"status": "not computed; no source path provided"}
    verify_inputs(report)
    return report


def compare_arms(a, b):
    if set(a) != set(b):
        raise ValueError("arm query IDs differ")
    ratios = [stats.median(b[q][r]["duration_ns"] for r in range(1, 6)) /
              stats.median(a[q][r]["duration_ns"] for r in range(1, 6)) for q in sorted(a)]
    identical = sum(all(quality(a[q][r]) == quality(b[q][r]) for r in range(1, 6)) for q in a)
    stable = sum(len({quality(arm[q][r]) for arm in (a, b) for r in range(1, 6)}) == 1 for q in a)
    return {"paired_query_count": len(a), "median_paired_B_over_A_query_median_latency": stats.median(ratios),
            "quality_identical_query_count": identical, "quality_changed_query_count": len(a) - identical,
            "quality_stable_across_arms_and_repetitions_count": stable,
            "quality_unstable_across_arms_or_repetitions_count": len(a) - stable}


def directional_support(comparisons):
    """Strict two-metric directional criterion in both builds, not a p-value."""
    if {c["build_number"] for c in comparisons} != {1, 2} or len(comparisons) != 2:
        raise ValueError("directional criterion requires exactly two distinct builds")
    timing = all(c["B_abs_log2_first_later"] < c["A_abs_log2_first_later"] and
                 c["B_later_pass_max_over_min"] < c["A_later_pass_max_over_min"] for c in comparisons)
    quality_preserved = all(c["quality_changed_query_count"] == 0 and
                            c["quality_unstable_across_arms_or_repetitions_count"] == 0 for c in comparisons)
    return {"timing_directional_criterion_both_builds": timing,
            "quality_preserved_both_builds": quality_preserved,
            "supported_without_quality_change": timing and quality_preserved}


def analyze_pilot(run_path):
    run = Path(run_path).resolve()
    inputs = [{"path": str(run), "sha256": snapshot(run)}]
    report = {"schema_version": 1, "kind": "preparation_policy_pilot", "interpretation": CAUTION,
              "provenance": provenance(inputs), "conditions": [], "arm_comparisons": [],
              "directional_support": [], "preparation": []}
    measured, warmup = query_ids(read_json(run / "queries.json"))
    config = read_json(run / "config.json")
    if json.dumps(config, sort_keys=True, separators=(",", ":")) != json.dumps(
        read_json(ROOT / "config/preparation-policy-v1.json"), sort_keys=True, separators=(",", ":")
    ):
        raise ValueError("pilot configuration differs from frozen repository profile")
    report["protocol"] = config
    rows, prep = read_rows(run / "executions.jsonl"), read_rows(run / "preparation.jsonl")
    if any(row.get("run_id") != run.name for row in rows + prep):
        raise ValueError("pilot observation run identity mismatch")
    keys = {(build, arm, m, f) for build in (1, 2) for arm in ("A", "B") for m, f in CONDITIONS}
    def key(row):
        integer(row["build_number"], "build_number", 1)
        return row["build_number"], row["arm"], row["method"], row["filter_threshold"]
    if any(row.get("phase") != "measured" for row in rows):
        raise ValueError("wrong measured phase")
    groups = group_measured(rows, key, keys, measured)
    sequences = [integer(row["sequence_index"], "sequence_index", 1) for row in rows + prep]
    if len(sequences) != 67200 or set(sequences) != set(range(1, 67201)):
        raise ValueError("global measured/preparation sequence is not complete and unique")
    validate_pilot_schedule(rows, prep, read_json(run / "schedule.json"), measured, warmup)
    prep_groups = defaultdict(list)
    prep_seen = set()
    for row in prep:
        validate_row(row, measured=False)
        group = key(row)
        phase = row["phase"]
        ids = warmup if phase == "disjoint_warmup" else measured
        if group not in keys or phase not in ("disjoint_warmup", "measured_exposure") or row["query_id"] not in ids or (phase == "measured_exposure" and row["arm"] != "B"):
            raise ValueError("preparation outside declared grid")
        identity = (*group, phase, row["query_id"])
        if identity in prep_seen:
            raise ValueError("duplicate preparation query")
        prep_seen.add(identity); prep_groups[(*group, phase)].append(row)
    expected_prep = {(*k, phase) for k in keys for phase in
                     (("disjoint_warmup", "measured_exposure") if k[1] == "B" else ("disjoint_warmup",))}
    if set(prep_groups) != expected_prep or any(len(values) != (20 if k[-1] == "disjoint_warmup" else 200) for k, values in prep_groups.items()):
        raise ValueError("incomplete preparation grid")
    for k in sorted(keys):
        build, arm, method, threshold = k
        report["conditions"].append({"build_number": build, "arm": arm,
            "method": method, "filter_threshold": threshold, **summarize_condition(groups[k])})
    index = {(c["build_number"], c["arm"], c["method"], c["filter_threshold"]): c for c in report["conditions"]}
    for build in (1, 2):
        for method, threshold in CONDITIONS:
            a, b = index[(build, "A", method, threshold)], index[(build, "B", method, threshold)]
            report["arm_comparisons"].append({"build_number": build, "method": method,
                "filter_threshold": threshold,
                **compare_arms(groups[(build, "A", method, threshold)], groups[(build, "B", method, threshold)]),
                "A_abs_log2_first_later": a["median_abs_log2_first_over_later"],
                "B_abs_log2_first_later": b["median_abs_log2_first_over_later"],
                "A_later_pass_max_over_min": a["later_pass_max_over_min"],
                "B_later_pass_max_over_min": b["later_pass_max_over_min"]})
    for method, threshold in CONDITIONS:
        relevant = [c for c in report["arm_comparisons"] if (c["method"], c["filter_threshold"]) == (method, threshold)]
        report["directional_support"].append({"method": method, "filter_threshold": threshold,
                                             **directional_support(relevant)})
    for k, values in sorted(prep_groups.items()):
        build, arm, method, threshold, phase = k
        times = [row["duration_ns"] for row in values]
        report["preparation"].append({"build_number": build, "arm": arm, "method": method,
            "filter_threshold": threshold, "phase": phase, "query_count": len(times),
            "total_seconds": sum(times) / 1e9, "median_ms": stats.median(times) / 1e6,
            "raw_request_p95_ms": percentile(times) / 1e6})
    report["counts"] = {"measured": len(rows), "preparation": len(prep), "conditions": len(groups),
                        "query_ids_per_condition": len(measured), "distinct_graph_builds": 2}
    report["criterion"] = "B must strictly reduce median absolute log2(first/later) AND later-pass max/min in BOTH builds. Quality equality is reported separately and gates supported_without_quality_change. This is an engineering directional criterion, not significance."
    verify_inputs(report)
    return report


def validate_pilot_schedule(rows, prep, schedule, measured, warmup):
    """Independently reconstruct preregistered permutations and full chronology."""
    def ordered(domain, values):
        return sorted(values, key=lambda value: (hashlib.sha256(f"{domain}|{value}".encode()).digest(), str(value)))
    block_keys = ordered("prep-block-v1", [f"{method}|{threshold}" for method, threshold in CONDITIONS])
    expected_builds, chronological = [], []
    for build in (1, 2):
        arms = ["A", "B"] if build == 1 else ["B", "A"]
        blocks = []
        for index, value in enumerate(block_keys if build == 1 else reversed(block_keys), 1):
            method, threshold = value.split("|"); threshold = int(threshold)
            blocks.append({"block_index": index, "method": method, "filter_threshold": threshold,
                "query_order_by_repetition": [ordered(f"prep-query-v1|{build}|{r}", measured) for r in range(1, 6)],
                "exposure_query_order": ordered(f"prep-exposure-v1|{build}", measured)})
        expected_builds.append({"build_number": build, "arms": arms, "blocks": blocks})
        for arm in arms:
            for block in blocks:
                prefix = (build, arm, block["method"], block["filter_threshold"])
                chronological.extend((*prefix, "disjoint_warmup", q, 0) for q in warmup)
                if arm == "B":
                    chronological.extend((*prefix, "measured_exposure", q, 0) for q in block["exposure_query_order"])
                for repetition, ids in enumerate(block["query_order_by_repetition"], 1):
                    chronological.extend((*prefix, "measured", q, repetition) for q in ids)
    if schedule != {"protocol_id": "preparation-policy-100k-v1", "builds": expected_builds}:
        raise ValueError("stored schedule differs from independent frozen permutations")
    observed = [(row["build_number"], row["arm"], row["method"], row["filter_threshold"], row["phase"],
                 row["query_id"], row["repetition"] if row["phase"] == "measured" else 0)
                for row in sorted(rows + prep, key=lambda row: row["sequence_index"])]
    if observed != chronological:
        raise ValueError("execution chronology differs from frozen schedule")


def markdown(report):
    pilot = report["kind"] == "preparation_policy_pilot"
    lines = ["# Preparation-policy pilot analysis" if pilot else "# Historical repetition reanalysis", "", CAUTION, "",
        "Primary latency: median across 200 per-query medians of all five repetitions. Query-median p95 is not request p95; each pass also reports its raw-request p95 separately. Ratios are paired within query. The 20% flag checks each pass median divided by the median across per-query medians of repetitions 2–5, outside [0.8, 1.2]. It is an engineering flag, not a statistical test.", "",
        "## All conditions", "",
        "| Build/arm | Method | Filter | Pass medians 1–5 ms | Pass request p95s ms | Primary median / query-median p95 ms | Paired first/later | Median absolute log2 | Later max/min | 20% flag | Recall canonical / tie | Complete |",
        "|---|---|---:|---|---|---|---:|---:|---:|---|---|---:|"]
    if pilot:
        lines[4:4] = [
            "Arm A: 20 disjoint warmup queries per method/filter block. Arm B: the same 20 warmups plus one exposure to all 200 measured queries before the five retained repetitions. Build 1 runs A then B; build 2 runs B then A. Arms within a build share the graph, with verified shared-buffer eviction before each arm; OS cache is not flushed. This is an operational preparation-policy comparison, not a cold-cache test.", ""]
    for c in report["conditions"]:
        values = lambda name: ", ".join(f"{v:.3f}" for v in c[name])
        lines.append(f"| {c['build_number']}/{c.get('arm', 'historical')} | {c['method']} | {c['filter_threshold']}% | {values('pass_median_ms')} | {values('pass_raw_request_p95_ms')} | {c['all_five_median_query_median_ms']:.3f} / {c['all_five_p95_query_median_ms']:.3f} | {c['median_paired_first_over_later']:.3f} | {c['median_abs_log2_first_over_later']:.3f} | {c['later_pass_max_over_min']:.3f} | {c['engineering_20pct_flag']} | {c['mean_canonical_recall_at_10']:.4f} / {c['mean_tie_aware_recall_at_10']:.4f} | {c['returned_k_rate']:.1%} |")
    if pilot:
        lines += ["", "## Matched arm comparison (each build kept separate)", "", report["criterion"], "",
                  "| Build | Method | Filter | Median paired B/A query latency | Quality-identical queries |", "|---:|---|---:|---:|---:|"]
        for c in report["arm_comparisons"]:
            lines.append(f"| {c['build_number']} | {c['method']} | {c['filter_threshold']}% | {c['median_paired_B_over_A_query_median_latency']:.3f} | {c['quality_identical_query_count']}/200 |")
        lines += ["", "## Prespecified directional criterion", "", "| Method | Filter | Both-build timing criterion | Quality preserved | Supported without quality change |", "|---|---:|---|---|---|"]
        for c in report["directional_support"]:
            lines.append(f"| {c['method']} | {c['filter_threshold']}% | {c['timing_directional_criterion_both_builds']} | {c['quality_preserved_both_builds']} | {c['supported_without_quality_change']} |")
        lines += ["", "## Preparation costs (not part of primary measured latency)", "", "| Build | Arm | Phase | Executions | Total query seconds |", "|---:|---|---|---:|---:|"]
        for build in (1, 2):
            for arm in ("A", "B"):
                for phase in ("disjoint_warmup", "measured_exposure"):
                    items = [c for c in report["preparation"] if (c["build_number"], c["arm"], c["phase"]) == (build, arm, phase)]
                    if items:
                        lines.append(f"| {build} | {arm} | {phase} | {sum(c['query_count'] for c in items)} | {sum(c['total_seconds'] for c in items):.3f} |")
        lines += ["", "Per-condition preparation costs and normalized pass values are retained in analysis.json. Query-call totals exclude validation, journaling, pauses, and other workflow overhead."]
    else:
        lines += ["", "## Exploratory prevalence", "", "```json", json.dumps(report["prevalence"], indent=2), "```", "",
                  "## Warmup versus measured query descriptors", "", "```json", json.dumps(report["query_features"], indent=2), "```"]
    lines += ["", "## Provenance and scope", "", f"Generator SHA-256: `{report['provenance']['generator_sha256']}`.", "",
              "Full artifact snapshots, source hashes where supplied, and code/worktree identity are in analysis.json. Input manifests are checked before and after analysis. This supplement does not replace source/ground-truth/query-plan verification.", ""]
    return "\n".join(lines)


def figures(report, output):
    """Static scientific figures; never run during database measurements."""
    with tempfile.TemporaryDirectory(prefix="preparation-matplotlib-") as cache:
        previous = os.environ.get("MPLCONFIGDIR")
        os.environ["MPLCONFIGDIR"] = cache
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            pilot = report["kind"] == "preparation_policy_pilot"
            columns = [(b, a) for b in (1, 2) for a in ("A", "B")] if pilot else [(1, None), (2, None)]
            index = {(c["build_number"], c.get("arm"), c["method"], c["filter_threshold"]): c for c in report["conditions"]}
            specifications = [("median_abs_log2_first_over_later", "First/later deviation: median |log2 ratio|", "first_later_deviation.png"),
                              ("later_pass_max_over_min", "Later-pass spread: maximum/minimum pass median", "later_pass_spread.png")]
            for field, title, name in specifications:
                values = [[index[(b, a, m, f)][field] for b, a in columns] for m, f in CONDITIONS]
                fig, ax = plt.subplots(figsize=(9, 8))
                mesh = ax.imshow(values, aspect="auto", cmap="YlOrRd", vmin=0 if "log2" in field else 1)
                for i, row in enumerate(values):
                    for j, value in enumerate(row):
                        ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=9)
                ax.set_xticks(range(len(columns)), [f"Build {b}" + (f" / {a}" if a else "") for b, a in columns])
                ax.set_yticks(range(15), [f"{m.replace('hnsw_', '')} / {f}%" for m, f in CONDITIONS])
                ax.set_title(title + "\nDescriptive; lower is more stable, not proof of steady state", fontsize=11)
                fig.colorbar(mesh, ax=ax, shrink=.8)
                footer = ("A: 20 disjoint warmups; B: same + 200 measured exposures. All five repetitions retained."
                          if pilot else "200 paired queries per cell; all five repetitions retained; builds shown separately")
                fig.text(.5, .01, footer, ha="center", fontsize=9)
                fig.tight_layout(rect=(0, .035, 1, 1)); fig.savefig(output / name, dpi=160); plt.close(fig)
            if pilot:
                fig, ax = plt.subplots(figsize=(9, 8))
                index = {(c["build_number"], c["method"], c["filter_threshold"]): c for c in report["arm_comparisons"]}
                for build, offset, marker in ((1, -.12, "o"), (2, .12, "s")):
                    values = [index[(build, m, f)]["median_paired_B_over_A_query_median_latency"] for m, f in CONDITIONS]
                    ax.scatter(values, [i + offset for i in range(15)], label=f"Build {build}", marker=marker)
                ax.axvline(1, color="gray", linestyle="--"); ax.set_xscale("log")
                ax.set_yticks(range(15), [f"{m.replace('hnsw_', '')} / {f}%" for m, f in CONDITIONS]); ax.invert_yaxis()
                ax.set_xlabel("Median paired B/A query-median latency (log scale); <1 means B faster")
                ax.set_title("Preparation-policy latency comparison\nAll five repetitions; no inference or pooled graph estimate")
                ax.legend(); ax.grid(axis="x", alpha=.3); fig.tight_layout()
                fig.savefig(output / "paired_latency_ratio.png", dpi=160); plt.close(fig)
            return {"matplotlib": matplotlib.__version__}
        finally:
            if previous is None:
                os.environ.pop("MPLCONFIGDIR", None)
            else:
                os.environ["MPLCONFIGDIR"] = previous


def generate(kind, paths, output, source=None):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing existing output: {output}")
    if "raw_results" in output.parts or any(Path(p).resolve() == output or Path(p).resolve() in output.parents for p in paths):
        raise ValueError("output must be outside raw results and inputs")
    if kind not in ("historical", "pilot") or (kind == "pilot" and (len(paths) != 1 or source is not None)):
        raise ValueError("invalid analysis mode or arguments")
    report = analyze_historical(paths, source) if kind == "historical" else analyze_pilot(paths[0])
    output.mkdir(parents=True, exist_ok=False)
    # If rendering or final verification fails, preserve partial output without COMPLETE.
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
                   "checksums_sha256": sha256(output / "checksums.sha256")}, handle, sort_keys=True)
        handle.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="kind", required=True)
    historical = sub.add_parser("historical")
    historical.add_argument("paths", nargs=2, type=Path)
    historical.add_argument("--source", type=Path)
    historical.add_argument("--output", required=True, type=Path)
    pilot = sub.add_parser("pilot")
    pilot.add_argument("paths", nargs=1, type=Path)
    pilot.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    generate(args.kind, args.paths, args.output, getattr(args, "source", None))
    print(args.output.resolve())
