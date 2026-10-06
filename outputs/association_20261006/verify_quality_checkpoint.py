"""Independent, standard-library-only arithmetic audit; never evaluates latency.

Reads the two completed first-build stages. This does not turn their disqualified
timing into eligible data, complete the four-stage design, or independently
recompute nearest neighbors from source vectors. The separate stage verifiers
provide the latter distance/ground-truth checks. No benchmark/analysis helpers
are imported here. Output creation is exclusive; historical files are untouched.
"""

from __future__ import annotations

import argparse
import array
from collections import defaultdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[2]
RUNS = ((100000, "20261006T175652Z_5367e3fe7857"),
        (250000, "20261006T180734Z_dcf7ada71ed5"))
FILTERS = (50, 20, 10, 5, 1)
MODES = ("legacy", "radial")
METHODS = ("exact", "hnsw_standard", "hnsw_iterative")
DATASET_SHA256 = "dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984"
METRICS = ("mean_canonical_recall_at_10", "mean_tie_aware_recall_at_10",
           "returned_10_rate", "mean_returned_count", "zero_result_rate")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(path):
    return json.loads(Path(path).read_text())


def lines(path):
    with Path(path).open() as handle:
        for line in handle:
            yield json.loads(line)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def int_bytes(values, typecode):
    result = array.array(typecode, values)
    require(result.itemsize == {"i": 4, "q": 8, "h": 2}[typecode], "unexpected integer platform")
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def check_manifest(run):
    require((run / "COMPLETE.json").is_file() and not (run / "ACTIVE").exists()
            and not (run / "INVALID.json").exists(), "expected completed immutable run")
    expected = {}
    for line in (run / "checksums.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(name not in expected and not Path(name).is_absolute() and ".." not in Path(name).parts,
                "duplicate or unsafe checksum path")
        expected[name] = digest
    excluded = {"COMPLETE.json", "INVALID.json", "ACTIVE", "checksums.sha256"}
    actual = {str(p.relative_to(run)): file_hash(p) for p in sorted(run.rglob("*"))
              if p.is_file() and p.name not in excluded}
    require(actual == expected, f"raw payload checksum or inventory mismatch: {run.name}")
    return {"payload_files": len(actual), "checksums_sha256": file_hash(run / "checksums.sha256"),
            "complete_marker_sha256": file_hash(run / "COMPLETE.json"),
            "payload_inventory_sha256": object_hash(actual)}


def ordered(domain, values, include_separator=True):
    prefix = domain + "|" if include_separator else domain
    return sorted(values, key=lambda value: (hashlib.sha256(f"{prefix}{value}".encode()).digest(), str(value)))


def close(actual, expected, label):
    require(type(actual) in (int, float) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12), f"arithmetic mismatch: {label}")


def recompute_stage(scale, run_id, global_order, query_order):
    run = ROOT / "raw_results/association" / run_id
    before = check_manifest(run)
    config, manifest = read(run / "config.json"), read(run / "manifest.json")
    dataset, selection = read(run / "dataset_manifest.json"), read(run / "scale_manifest.json")
    metadata, query_doc = read(run / "metadata_manifest.json"), read(run / "queries.json")
    require(config["scale_rows"] == scale and config["build_number"] == 1
            and config["methods"] == list(METHODS) and config["metadata_modes"] == list(MODES)
            and config["filter_thresholds"] == list(FILTERS) and config["k"] == 10
            and config["measured_query_count"] == 200 and config["warmup_query_count"] == 20
            and config["repetitions"] == 5, "unexpected first-build campaign grid")
    require(object_hash(config) == manifest["config_sha256"], "config hash mismatch")
    require(manifest["git_at_start"]["dirty"] is False and manifest["git_at_start"]["status_porcelain"] == [],
            "unclean source checkpoint")
    require(dataset["sha256"] == DATASET_SHA256 and dataset["byte_size"] == 525128288,
            "unexpected source dataset")
    selected = global_order[:scale]
    selected_set = set(selected)
    require(hashlib.sha256(int_bytes(selected, "i")).hexdigest() == selection["selected_base_ids_sha256"],
            "independently ranked base selection differs")
    require(hashlib.sha256(int_bytes(selected, "q")).hexdigest() == metadata["ordered_base_ids_int64_le_sha256"],
            "metadata ordered ID identity differs")
    membership = int_bytes(selected, "i") + int_bytes(range(scale), "i") + int_bytes((i % 100 for i in range(scale)), "h")
    require(hashlib.sha256(membership).hexdigest() == selection["membership_sha256"],
            "scale membership identity differs")
    counts = {str(t): scale * t // 100 for t in FILTERS}
    require(selection["filter_counts"] == counts and metadata["filter_counts"] == counts,
            "metadata manifest cardinalities differ")
    require(metadata["row_count"] == scale and metadata["anchor_source_base_id"] == 0,
            "metadata row/anchor provenance differs")
    measured_ids, warmup_ids = query_order[:200], query_order[200:220]
    require(query_doc["measured_query_ids"] == measured_ids and query_doc["warmup_query_ids"] == warmup_ids,
            "independently ranked query selection differs")
    require(set(measured_ids).isdisjoint(warmup_ids), "measured and warmup overlap")

    truths = {}
    for mode in MODES:
        records = list(lines(run / f"{mode}_ground_truth.jsonl"))
        require(len(records) == 1000, "ground-truth count differs")
        for record in records:
            key = mode, record["query_id"], record["filter_threshold"]
            require(key not in truths and record["metadata_mode"] == mode and record["scale_rows"] == scale
                    and record["k"] == 10 and record["run_id"] == run_id
                    and record["dataset_sha256"] == DATASET_SHA256
                    and record["metadata_sha256"] == object_hash(metadata), "truth provenance mismatch")
            body = {k: v for k, v in record.items() if k != "record_sha256"}
            require(object_hash(body) == record["record_sha256"], "truth record checksum differs")
            canonical = record["canonical_ids"]
            closer, boundary = set(record["strictly_closer_ids"]), set(record["boundary_tie_ids"])
            ids, distances = record["all_with_ties_ids"], record["all_with_ties_distances"]
            require(len(canonical) == len(set(canonical)) == 10 and len(ids) == len(set(ids)) == len(distances)
                    and len(closer) < 10 and not closer.intersection(boundary)
                    and closer.union(boundary) == set(ids) and set(ids) <= selected_set,
                    "invalid truth sets")
            pairs = sorted(zip(distances, ids))
            require(canonical == [identifier for _, identifier in pairs[:10]], "canonical tie ordering differs")
            require(record["canonical_distances"] == [distance for distance, _ in pairs[:10]],
                    "canonical distances disagree with complete exact result")
            require(record["qualifying_count"] == scale * key[2] // 100, "truth qualifying count differs")
            truths[key] = record
        require({(m, q, t) for m, q, t in truths if m == mode} ==
                {(mode, q, t) for q in measured_ids for t in FILTERS}, "incomplete truth grid")

    schedule = read(run / "schedule.json")
    keys = ordered("association-block-v1", [f"{m}|{t}" for m in METHODS for t in FILTERS])
    expected_blocks = []
    expected_sequences = []
    for block_index, key in enumerate(keys, 1):
        method, threshold = key.split("|")
        expected_blocks.append({"block_index": block_index, "method": method, "filter_threshold": int(threshold),
                                "query_order_by_repetition": [ordered(f"association-query-v1|1|{rep}", measured_ids)
                                                              for rep in range(1, 6)]})
    require(schedule == {"modes": list(MODES), "blocks": expected_blocks}, "frozen schedule differs")
    for mode in MODES:
        for block in expected_blocks:
            common = (mode, block["block_index"], block["method"], block["filter_threshold"])
            expected_sequences.extend((*common, "disjoint_warmup", 0, q) for q in warmup_ids)
            for rep, order in enumerate(block["query_order_by_repetition"], 1):
                expected_sequences.extend((*common, "measured", rep, q) for q in order)

    quality = defaultdict(dict)
    actual_sequences = {}
    recomputed_fields, warmups = 0, 0
    for filename, phase in (("executions.jsonl", "measured"), ("preparation.jsonl", "disjoint_warmup")):
        previous_sequence = 0
        for row in lines(run / filename):
            seq = row["sequence_index"]
            require(type(seq) is int and seq > previous_sequence and seq not in actual_sequences,
                    "duplicate or unordered observation")
            previous_sequence = seq
            require(row["run_id"] == run_id and row["scale_rows"] == scale and row["build_number"] == 1
                    and row["config_sha256"] == manifest["config_sha256"] and row["phase"] == phase,
                    "observation provenance differs")
            actual_sequences[seq] = tuple(row[k] for k in
                ("metadata_mode", "block_index", "method", "filter_threshold", "phase", "repetition", "query_id"))
            require(row["error_type"] is None and row["error_message"] is None and row["timeout"] is False,
                    "failed observation in complete run")
            ids, distances = row["result_ids"], row["distances"]
            count = len(ids)
            require(count <= 10 and count == len(distances) == len(set(ids)) and set(ids) <= selected_set,
                    "invalid returned IDs")
            require(all(math.isfinite(d) and d >= 0 for d in distances)
                    and all(a <= b + 1e-12 for a, b in zip(distances, distances[1:])), "invalid result distances")
            require(row["returned_count"] == count and row["returned_k"] is (count == 10)
                    and row["shortfall"] == 10 - count and all(row[k] is True for k in
                    ("ids_unique", "scale_valid", "filter_valid", "distance_order_valid")), "stored result count/flags differ")
            if phase == "disjoint_warmup":
                require(row["canonical_recall_at_10"] is None and row["tie_aware_recall_at_10"] is None
                        and row["ground_truth_record_sha256"] is None, "warmup falsely claims recall")
                warmups += 1
                continue
            exact = truths[row["metadata_mode"], row["query_id"], row["filter_threshold"]]
            returned = set(ids)
            canonical = len(returned.intersection(exact["canonical_ids"])) / 10
            closer, boundary = set(exact["strictly_closer_ids"]), set(exact["boundary_tie_ids"])
            tie = (len(returned & closer) + min(10 - len(closer), len(returned & boundary))) / 10
            close(row["canonical_recall_at_10"], canonical, "stored canonical recall")
            close(row["tie_aware_recall_at_10"], tie, "stored tie-aware recall")
            require(row["ground_truth_record_sha256"] == exact["record_sha256"], "row uses different exact truth")
            if row["method"] == "exact":
                require(ids == exact["canonical_ids"] and count == 10 and canonical == tie == 1,
                        "exact search differs from ground truth")
            key = row["metadata_mode"], row["method"], row["filter_threshold"], row["query_id"]
            require(row["repetition"] not in quality[key], "duplicate query repetition")
            quality[key][row["repetition"]] = {"mean_canonical_recall_at_10": canonical,
                "mean_tie_aware_recall_at_10": tie, "returned_10_rate": int(count == 10),
                "mean_returned_count": count, "zero_result_rate": int(count == 0),
                "ids": tuple(ids), "distances": tuple(distances)}
            recomputed_fields += 5
    require([actual_sequences[i] for i in range(1, 30601)] == expected_sequences
            and len(actual_sequences) == 30600 and warmups == 600, "execution grid differs")
    require(set(quality) == set(itertools.product(MODES, METHODS, FILTERS, measured_ids)), "quality cell grid differs")
    per_query, changed_quality, changed_ids_or_distances = {}, [], []
    for key, repetitions in quality.items():
        require(set(repetitions) == {1, 2, 3, 4, 5}, "query lacks all five repetitions")
        values = list(repetitions.values())
        per_query[key] = {metric: statistics.fmean(v[metric] for v in values) for metric in METRICS}
        if any(any(v[m] != values[0][m] for m in METRICS) for v in values[1:]):
            changed_quality.append(list(key))
        if any((v["ids"], v["distances"]) != (values[0]["ids"], values[0]["distances"]) for v in values[1:]):
            changed_ids_or_distances.append(list(key))
    conditions = []
    contrasts = []
    for mode, method, threshold in itertools.product(MODES, METHODS, FILTERS):
        cells = [per_query[mode, method, threshold, q] for q in measured_ids]
        conditions.append({"scale_rows": scale, "build_number": 1, "metadata_mode": mode,
                           "method": method, "filter_threshold": threshold,
                           "query_count": 200, "measured_executions": 1000,
                           "quality_stable_query_count": 200 - sum(k[:3] == [mode, method, threshold] for k in changed_quality),
                           "ordered_results_stable_query_count": 200 - sum(k[:3] == [mode, method, threshold] for k in changed_ids_or_distances),
                           **{metric: statistics.fmean(c[metric] for c in cells) for metric in METRICS}})
    for method, threshold in itertools.product(METHODS, FILTERS):
        metrics = {}
        for metric in METRICS:
            deltas = [per_query["radial", method, threshold, q][metric] - per_query["legacy", method, threshold, q][metric]
                      for q in measured_ids]
            metrics[metric] = {"radial_minus_legacy_mean": statistics.fmean(deltas),
                               "radial_minus_legacy_median": statistics.median(deltas),
                               "queries_positive": sum(v > 0 for v in deltas),
                               "queries_negative": sum(v < 0 for v in deltas),
                               "queries_unchanged": sum(v == 0 for v in deltas)}
        contrasts.append({"scale_rows": scale, "build_number": 1, "method": method,
                          "filter_threshold": threshold, "query_count": 200, "metrics": metrics})
    after = check_manifest(run)
    require(before == after, "raw artifact hashes changed during independent arithmetic")
    report = {"run_id": run_id, "scale_rows": scale, "build_number": 1, "passed": True,
              "raw_hashes_before": before, "raw_hashes_after": after, "source_commit": manifest["expected_source_commit"],
              "measured_rows_recomputed": 30000, "warmup_rows_checked": warmups,
              "truth_records_checked": len(truths), "metric_fields_recomputed": recomputed_fields,
              "query_quality_cells": len(quality), "quality_changed_across_repetitions": changed_quality,
              "ordered_ids_or_distances_changed_across_repetitions": changed_ids_or_distances,
              "conditions": conditions, "paired_mode_contrasts": contrasts,
              "source_selection_and_schedule_independently_reconstructed": True,
              "dataset_path": dataset["path"], "source_file_sha256": manifest["source_file_sha256"],
              "metadata_manifest": metadata, "query_manifest": query_doc, "_per_query": per_query}
    return report


def compare_derived(stages, path):
    """Compare the published quality projection without importing its producer."""
    initial_hash = file_hash(path)
    derived = read(path)
    require(derived["campaign_complete"] is False
            and derived["timing_use_disposition"].startswith("DISQUALIFIED"), "incorrect checkpoint interpretation")
    field_map = {"mean_canonical_recall_at_10": "mean_canonical_recall_at_10",
                 "mean_tie_aware_recall_at_10": "mean_tie_aware_recall_at_10",
                 "returned_10_rate": "returned_k_rate", "mean_returned_count": "mean_returned_count"}
    query_map = {"mean_canonical_recall_at_10": "canonical_recall_at_10",
                 "mean_tie_aware_recall_at_10": "tie_aware_recall_at_10",
                 "returned_10_rate": "returned_k", "mean_returned_count": "returned_count"}
    published = {}
    for condition in derived["conditions"]:
        key = tuple(condition[k] for k in ("scale_rows", "build_number", "metadata_mode", "method", "filter_threshold"))
        require(key not in published, "duplicate published condition")
        published[key] = condition
    expected_keys = {(s["scale_rows"], 1, m, method, t) for s in stages for m in MODES for method in METHODS for t in FILTERS}
    require(set(published) == expected_keys, "published condition grid differs")
    compared_fields = 0
    for stage in stages:
        for independent in stage["conditions"]:
            key = tuple(independent[k] for k in ("scale_rows", "build_number", "metadata_mode", "method", "filter_threshold"))
            condition = published[key]
            require(condition["run_id"] == stage["run_id"] and condition["query_count"] == 200
                    and condition["execution_count"] == 1000, "published condition provenance/counts differ")
            for field, target in field_map.items():
                close(condition[target], independent[field], f"condition {key}/{target}")
                compared_fields += 1
            for field in ("quality_stable_query_count", "ordered_results_stable_query_count"):
                close(condition[field], independent[field], f"condition {key}/{field}")
                compared_fields += 1
            rows = condition["density_quality"]["query_records"]
            expected_queries = {q for mode, method, t, q in stage["_per_query"] if (mode, method, t) == key[2:]}
            require(len(rows) == 200 and {r["query_id"] for r in rows} == expected_queries,
                    "published per-query condition grid differs")
            for row in rows:
                independent_query = stage["_per_query"][*key[2:], row["query_id"]]
                for field, target in query_map.items():
                    close(row[target], independent_query[field], f"condition query {key}/{row['query_id']}/{target}")
                    compared_fields += 1
    contrasts = {}
    for contrast in derived["metadata_quality_comparisons"]:
        key = tuple(contrast[k] for k in ("scale_rows", "build_number", "method", "filter_threshold"))
        require(key not in contrasts, "duplicate published contrast")
        contrasts[key] = contrast
    require(set(contrasts) == {(s["scale_rows"], 1, method, t) for s in stages for method in METHODS for t in FILTERS},
            "published contrast grid differs")
    for stage in stages:
        for independent in stage["paired_mode_contrasts"]:
            key = tuple(independent[k] for k in ("scale_rows", "build_number", "method", "filter_threshold"))
            contrast = contrasts[key]
            require(contrast["run_id"] == stage["run_id"] and contrast["query_count"] == 200,
                    "published contrast provenance differs")
            for field, target in query_map.items():
                ours = independent["metrics"][field]
                theirs = contrast["paired_quality_deltas"][target]
                for own_name, their_name in (("radial_minus_legacy_mean", "mean"),
                    ("radial_minus_legacy_median", "median"), ("queries_positive", "positive_query_count"),
                    ("queries_negative", "negative_query_count"), ("queries_unchanged", "zero_query_count")):
                    close(theirs[their_name], ours[own_name], f"paired {key}/{target}/{their_name}")
                    compared_fields += 1
            rows = contrast["paired_query_records"]
            expected_queries = {q for mode, method, t, q in stage["_per_query"] if (method, t) == key[2:]}
            require(len(rows) == 200 and {r["query_id"] for r in rows} == expected_queries,
                    "published paired query grid differs")
            for row in rows:
                baseline = stage["_per_query"]["legacy", *key[2:], row["query_id"]]
                radial = stage["_per_query"]["radial", *key[2:], row["query_id"]]
                for field, target in query_map.items():
                    close(row[f"radial_minus_legacy_{target}"], radial[field] - baseline[field],
                          f"paired query {key}/{row['query_id']}/{target}")
                    compared_fields += 1
    require(file_hash(path) == initial_hash, "published quality JSON changed during verification")
    return {"passed": True, "path": str(path.resolve()), "sha256_before": initial_hash,
            "sha256_after": file_hash(path), "numeric_fields_compared": compared_fields,
            "discrepancies": 0, "absolute_tolerance": 1e-12,
            "scope": "all condition quality means and repeat stability counts; all per-query quality values; all mode-pair quality summaries and query differences",
            "not_checked_by_this_comparison": "density group arithmetic, rank correlations, figure rendering or any timing"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new exclusive JSON output path")
    parser.add_argument("--reference", type=Path,
                        default=ROOT / "outputs/association_20261006/quality_checkpoint/QUALITY_CHECKPOINT.json")
    args = parser.parse_args()
    require(not args.output.exists(), "refusing to replace an existing independent proof")
    require(args.reference.is_file(), "published quality-only checkpoint must exist before independent comparison")
    global_order = ordered("sift-base-v1", range(1000000))
    query_order = ordered("sift-query-v1", range(10000))
    stages = [recompute_stage(scale, run_id, global_order, query_order) for scale, run_id in RUNS]
    small, large = stages
    require(small["source_file_sha256"] == large["source_file_sha256"], "matched source implementation bytes differ")
    require(small["query_manifest"] == large["query_manifest"], "query vectors/selection differ across scales")
    require(small["metadata_manifest"]["radial_labels_int16_le_sha256"] ==
            large["metadata_manifest"]["prefix_100k_radial_labels_int16_le_sha256"], "inherited labels differ")
    require(small["metadata_manifest"]["ordered_base_ids_int64_le_sha256"] ==
            large["metadata_manifest"]["prefix_100k_ordered_base_ids_int64_le_sha256"], "inherited row order differs")
    require(small["dataset_path"] == large["dataset_path"], "source paths differ")
    dataset_path = Path(small["dataset_path"])
    require(dataset_path.stat().st_size == 525128288 and file_hash(dataset_path) == DATASET_SHA256,
            "pinned actual source file bytes differ")
    comparison = compare_derived(stages, args.reference)
    for stage in stages:
        for private in ("source_file_sha256", "metadata_manifest", "query_manifest", "dataset_path", "_per_query"):
            stage.pop(private)
    report = {"schema_version": 1, "passed": True, "audit_script_sha256": file_hash(Path(__file__)),
              "independence": "standard library only; no benchmark or analysis imports",
              "scope": "retrieval arithmetic, exact-record internal integrity, source bytes/selection, schedule and repeat consistency",
              "not_recomputed_here": "Source-vector nearest-neighbor search, physical-table metadata equality, radial ranks, HNSW plans and association diagnostics are covered by the separate stage verifiers.",
              "timing_eligible": False, "timing_values_analyzed": 0,
              "interpretation": "Two first-build stages only; one physical graph per scale. All timings are disqualified. No final findings or completed four-stage campaign.",
              "source_sha256": DATASET_SHA256, "matched_implementation_bytes": True,
              "same_queries": True, "inherited_100k_row_order_and_radial_labels": True,
              "condition_count": 60, "paired_mode_contrast_count": 30,
              "measured_rows_recomputed": 60000, "ground_truth_records_checked": 4000,
              "derived_quality_comparison": comparison, "stages": stages}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(json.dumps({k: report[k] for k in ("passed", "condition_count", "paired_mode_contrast_count",
                                           "measured_rows_recomputed", "ground_truth_records_checked", "timing_values_analyzed")}, sort_keys=True))


if __name__ == "__main__":
    main()
