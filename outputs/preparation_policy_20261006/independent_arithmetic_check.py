#!/usr/bin/env python3
"""Read-only independent arithmetic audit of the frozen preparation-policy pilot.

Run from the repository root:
  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python \\
    outputs/preparation_policy_20261006/independent_arithmetic_check.py

This checker uses NumPy reductions instead of importing any project producer or
analysis helper. It compares 60 condition summaries, 30 within-build arm pairs,
15 directional-support records, and 90 preparation summaries. It separately
derives the stricter operational acceptance rule. It writes nothing. Integrity,
source-distance, ground-truth, plan, and provenance checks belong to the separate
offline verifier; agreement here is arithmetic consistency, not causal proof.
"""
import json, math, hashlib
from pathlib import Path
from collections import defaultdict
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
base=ROOT/Path("raw_results/preparation_policy/20261006T085044Z_5791f42860c1")
rows=[json.loads(s) for s in (base/"executions.jsonl").read_text().splitlines()]
prep=[json.loads(s) for s in (base/"preparation.jsonl").read_text().splitlines()]
g=defaultdict(dict)
qfields=("result_ids","distances","canonical_recall_at_10","tie_aware_recall_at_10","returned_k","returned_count")
def qual(r): return json.dumps([r[x] for x in qfields],separators=(",",":"))
for r in rows:
 k=(r["build_number"],r["arm"],r["method"],r["filter_threshold"])
 cell=(r["query_id"],r["repetition"])
 assert cell not in g[k]
 g[k][cell]=r
assert len(rows)==60000 and len(g)==60
results={}; arrays={}
for k, data in sorted(g.items()):
 qs=sorted({q for q,r in data}); assert len(qs)==200
 assert len(data)==1000
 a=np.array([[data[q,r]["duration_ns"] for r in range(1,6)] for q in qs],dtype=np.float64)
 allmed=np.median(a,axis=1); latermed=np.median(a[:,1:],axis=1)
 ratio=a[:,0]/latermed
 passmed=np.median(a,axis=0); normal=passmed/np.median(latermed)
 vals=list(data.values())
 result=dict(query_count=200,execution_count=1000,
   pass_median_ms=(passmed/1e6).tolist(),
   pass_raw_request_p95_ms=(np.percentile(a,95,axis=0,method="linear")/1e6).tolist(),
   all_five_median_query_median_ms=float(np.median(allmed)/1e6),
   all_five_p95_query_median_ms=float(np.percentile(allmed,95,method="linear")/1e6),
   median_paired_first_over_later=float(np.median(ratio)),
   median_abs_log2_first_over_later=float(np.median(np.abs(np.log2(ratio)))),
   later_pass_max_over_min=float(np.max(passmed[1:])/np.min(passmed[1:])),
   normalization_later_median_query_median_ms=float(np.median(latermed)/1e6),
   all_pass_normalized_medians=normal.tolist(),
   engineering_20pct_flag=bool(np.any((normal<.8)|(normal>1.2))),
   ordered_results_stable_query_count=sum(len({tuple(data[q,r]["result_ids"]) for r in range(1,6)})==1 for q in qs),
   quality_stable_query_count=sum(len({qual(data[q,r]) for r in range(1,6)})==1 for q in qs),
   mean_canonical_recall_at_10=float(np.mean([x["canonical_recall_at_10"] for x in vals])),
   mean_tie_aware_recall_at_10=float(np.mean([x["tie_aware_recall_at_10"] for x in vals])),
   returned_k_rate=float(np.mean([x["returned_k"] for x in vals])),
   mean_returned_count=float(np.mean([x["returned_count"] for x in vals])))
 results[k]=result; arrays[k]=(qs,allmed)
comparisons={}
for build in (1,2):
 for method in ("exact","hnsw_standard","hnsw_iterative"):
  for threshold in (1,5,10,20,50):
   key=(build,method,threshold); ka=(build,"A",method,threshold); kb=(build,"B",method,threshold)
   qs,am=arrays[ka]; qb,bm=arrays[kb]; assert qs==qb
   ac,bc=g[ka],g[kb]; a,b=results[ka],results[kb]
   identical=sum(all(qual(ac[q,r])==qual(bc[q,r]) for r in range(1,6)) for q in qs)
   stable=sum(len({qual(x[q,r]) for x in (ac,bc) for r in range(1,6)})==1 for q in qs)
   comparisons[key]=dict(paired_query_count=200,median_paired_B_over_A_query_median_latency=float(np.median(bm/am)),
       quality_identical_query_count=identical,quality_changed_query_count=200-identical,
       quality_stable_across_arms_and_repetitions_count=stable,quality_unstable_across_arms_or_repetitions_count=200-stable,
       A_abs_log2_first_later=a["median_abs_log2_first_over_later"],B_abs_log2_first_later=b["median_abs_log2_first_over_later"],
       A_later_pass_max_over_min=a["later_pass_max_over_min"],B_later_pass_max_over_min=b["later_pass_max_over_min"])
support={}; acceptance={}
for method in ("exact","hnsw_standard","hnsw_iterative"):
 for threshold in (1,5,10,20,50):
  cs=[comparisons[(n,method,threshold)] for n in (1,2)]
  direction=all(c["B_abs_log2_first_later"]<c["A_abs_log2_first_later"] and c["B_later_pass_max_over_min"]<c["A_later_pass_max_over_min"] for c in cs)
  preserved=all(c["quality_changed_query_count"]==c["quality_unstable_across_arms_or_repetitions_count"]==0 for c in cs)
  support[(method,threshold)]=dict(timing_directional_criterion_both_builds=direction,quality_preserved_both_builds=preserved,supported_without_quality_change=direction and preserved)
  acceptance[(method,threshold)]=direction and preserved and not any(results[n,"B",method,threshold]["engineering_20pct_flag"] for n in (1,2))
analysis=ROOT/Path("outputs/preparation_policy_20261006/pilot_analysis/analysis.json")
assert analysis.is_file(), "canonical analysis.json must exist"
mismatches=[]; comparisons_checked=0
def compare(label,expected,observed):
 global comparisons_checked
 for field,value in expected.items():
  ov=observed[field]
  if isinstance(value,list):
   ok=np.allclose(value,ov,rtol=1e-12,atol=1e-12)
  elif isinstance(value,bool) or isinstance(value,int): ok=(type(ov)==type(value) and ov==value)
  else: ok=math.isclose(value,ov,rel_tol=1e-12,abs_tol=1e-12)
  comparisons_checked+=1
  if not ok: mismatches.append([label,field,value,ov])
if analysis.exists():
 out=json.loads(analysis.read_text())
 assert len(out["conditions"])==60 and {(c["build_number"],c["arm"],c["method"],c["filter_threshold"]) for c in out["conditions"]}==set(results)
 assert len(out["arm_comparisons"])==30 and {(c["build_number"],c["method"],c["filter_threshold"]) for c in out["arm_comparisons"]}==set(comparisons)
 assert len(out["directional_support"])==15 and {(c["method"],c["filter_threshold"]) for c in out["directional_support"]}==set(support)
 for c in out["conditions"]:
  key=c["build_number"],c["arm"],c["method"],c["filter_threshold"]
  compare(str(key),results[key],c)
 for c in out["arm_comparisons"]:
  key=c["build_number"],c["method"],c["filter_threshold"]
  compare(str(key),comparisons[key],c)
 for c in out["directional_support"]:
  compare(str((c["method"],c["filter_threshold"])),support[c["method"],c["filter_threshold"]],c)
condition_field_comparisons=comparisons_checked
prep_groups=defaultdict(list)
prep_totals=defaultdict(lambda: {"execution_count":0,"duration_ns":0})
for r in prep:
 key=r["build_number"],r["arm"],r["method"],r["filter_threshold"],r["phase"]
 prep_groups[key].append(r["duration_ns"])
 bucket=prep_totals[r["build_number"],r["arm"],r["phase"]]
 bucket["execution_count"]+=1; bucket["duration_ns"]+=r["duration_ns"]
assert len(prep_groups)==90 and len(out["preparation"])==90
assert {(c["build_number"],c["arm"],c["method"],c["filter_threshold"],c["phase"]) for c in out["preparation"]}==set(prep_groups)
for c in out["preparation"]:
 key=c["build_number"],c["arm"],c["method"],c["filter_threshold"],c["phase"]
 values=prep_groups[key]
 expected=dict(query_count=len(values),total_seconds=sum(values)/1e9,
  median_ms=float(np.median(values))/1e6,
  raw_request_p95_ms=float(np.percentile(values,95,method="linear"))/1e6)
 compare(str(key),expected,c)
preparation_field_comparisons=comparisons_checked-condition_field_comparisons
assert condition_field_comparisons==1425 and preparation_field_comparisons==360
resource=[s["host"] for p in sorted(base.glob("*_resource_snapshots.json")) for s in json.loads(p.read_text())]
resources=dict(snapshot_count=len(resource),memory_total_bytes=sorted({r["memory_total_bytes"] for r in resource}),
 memory_available_bytes_min_max=[min(r["memory_available_bytes"] for r in resource),max(r["memory_available_bytes"] for r in resource)],
 disk_free_bytes_min_max=[min(r["disk_free_bytes"] for r in resource),max(r["disk_free_bytes"] for r in resource)],
 process_max_rss_max=max(r["process_max_rss"] for r in resource),logical_cpu_count=sorted({r["logical_cpu_count"] for r in resource},key=str),
 physical_cpu_count=sorted({r["physical_cpu_count"] for r in resource}),client_machine=sorted({r["machine"] for r in resource}),
 caveat="Process lifetime maximum RSS is runner only, not PostgreSQL or system total; snapshots do not identify swapping, physical disk I/O, or background process causes.")
print(json.dumps(dict(audit="independent NumPy/standard-library arithmetic; no project analysis import",rows=len(rows),conditions=len(results),
 canonical_analysis_present=analysis.exists(),condition_and_comparison_field_comparisons=condition_field_comparisons,preparation_field_comparisons=preparation_field_comparisons,total_field_comparisons=comparisons_checked,mismatches=mismatches,
 engineering_flag_counts={f"b{n}_{arm}":sum(c["engineering_20pct_flag"] for (nn,aa,m,f),c in results.items() if nn==n and aa==arm) for n in (1,2) for arm in ("A","B")},
 flagged_conditions=[dict(build=k[0],arm=k[1],method=k[2],filter=k[3],first_later=v["median_paired_first_over_later"],later_range=v["later_pass_max_over_min"],passes_ms=v["pass_median_ms"]) for k,v in results.items() if v["engineering_20pct_flag"]],
 directional_support=[dict(method=k[0],filter=k[1],**v,operational_acceptance=acceptance[k]) for k,v in support.items()],
 quality_all_12000_query_cells_stable=all(c["quality_stable_query_count"]==200 for c in results.values()),
 quality_all_6000_matched_queries_stable=all(c["quality_stable_across_arms_and_repetitions_count"]==200 for c in comparisons.values()),
 query_times_seconds=dict(measured=sum(x["duration_ns"] for x in rows)/1e9,preparation=sum(x["duration_ns"] for x in prep)/1e9),
 preparation_totals=[dict(build=k[0],arm=k[1],phase=k[2],execution_count=v["execution_count"],total_seconds=v["duration_ns"]/1e9) for k,v in sorted(prep_totals.items())],
 resources=resources,
 relation_sizes_by_build={str(n):json.loads((base/f"b{n}_database_evidence.json").read_text())["relation_sizes"] for n in (1,2)},
 phase_metrics={str(n):json.loads((base/f"b{n}_phase_metrics.json").read_text()) for n in (1,2)}),indent=2))
if mismatches:
 raise SystemExit("Independent arithmetic disagrees with canonical analysis")
