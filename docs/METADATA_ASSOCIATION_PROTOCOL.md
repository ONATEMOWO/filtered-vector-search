# Matched metadata association and first scale progression

Frozen before new geometric diagnostics or ANN outcomes. Starting checkpoint:
`d3bcae685e2f61679e7dc1b7b230264480dffce1`. Historical artifacts/profiles and
the A5 PDF are preserved. The original worktree's old invalid-run failure.json
formatting edit remains unrelated and uncommitted.

## Core question and scope

At fixed global selectivity, does controlled concentration of qualifying rows
near a fixed vector anchor change recall, completeness and operational latency
of exact, standard HNSW and strict iterative HNSW? Do those paired contrasts
persist when physical scale increases from 100k to 250k with inherited metadata
labels and the same queries?

The proposed mechanism is query-local qualifying-neighbor density. Some query
neighborhoods may be enriched and others depleted. Standard postfiltered HNSW
may consequently return different numbers of qualifying neighbors; iterative
scanning may compensate at additional cost. No universal direction of average
recall or latency is stipulated. Strong measured association with little change
in retrieval, or inconsistent changes across builds/scales, complicates the
hypothesis and is retained.

Candidates considered: another timing intervention, scale alone, offline query
analysis, and a controlled association contrast with a matched next scale.
Choose the last: it addresses instructor feedback and a central omitted
variable while reusing existing correctness machinery. Timing uncertainty is
bounded by descriptive reporting, not treated as a reason to postpone all
research. No additional measured-query exposure is used or retuned.

## Deterministic metadata: global cardinality versus local geometry

Keep the existing SHA256-ranked nested SIFT base subsets and historical
`filter_bucket = scale_rank % 100`. Call this **content-blind baseline**, not
proven independent metadata.

For the second mode, choose training vector base_id=0 as a fixed anchor before
looking at outcomes. Compute each base vector's float64 squared L2 distance to
that anchor. Divide the existing hash order into consecutive blocks of 100.
Within each block sort by (squared anchor distance, base ID), assigning
`radial_bucket = 0..99`. Thresholds below 50/20/10/5/1 therefore select exactly
the same global counts as the baseline. Labels on existing IDs are unchanged
when another complete block is added; vectors and filters nest across scales.

This is **block-balanced radial-rank synthetic metadata**, not k-means clusters,
semantic labels or global geometric quantiles. Within-block quantile noise is
intentional: it preserves exact counts and inherited labels without scale-
specific relabeling. An anchor and 100-row block size are frozen, not chosen by
retrieval outcomes. A separate random projection and large-shell quantiles were
considered but add arbitrary direction or scale-boundary-specific machinery.
No query vector is used in metadata assignment.

Both columns are loaded before any HNSW build. Both modes query the SAME exact
and ANN heaps and SAME graph in each stage; there are no metadata UPDATEs or
mode-specific HNSW rebuilds. A separate `association` schema leaves historical
`milestone2` and Milestone 1 tables intact. The exact table has one B-tree per
metadata column; the ANN table has neither. Plan differences in exact search
are a legitimate configured-system outcome and are recorded.

## Manipulation check before timed execution

From source vectors independently compute exact unfiltered top-1000 neighbors
for all 200 measured and 20 disjoint warmup queries, with squared-distance/ID
ordering. Record qualifying counts at L=40,100,1000 for both modes/all filters.
L=100 is primary. Source distances and memberships are independently checked.

For selectivity s, report local qualifying fraction p(q,L), enrichment p/s,
zero-density proportion, mean, variance and quantiles. Primary geometric
deviation D_s = mean over 200 measured queries of (p(q,100)-s)^2; decompose it
into variance plus squared mean displacement. Pure variance can miss uniformly
depleted query neighborhoods. Warmups are reported separately, not pooled.

Use 99 PCG64 permutations (seed 20261006) that shuffle labels within each
100-row block while retaining overlapping-neighborhood dependence and exact
counts. For the predeclared 50% and 5% conditions require radial D_s to exceed
both baseline D_s and the linear-interpolated 95th percentile of the permutation
reference. This is an engineering manipulation check, not a population
significance test. Report all filters regardless. Failure is preserved and
stops expansion; do not choose another anchor or loosen the criterion.

Exact top-40 density is a descriptive proxy near the fixed ef_search scale,
NOT pgvector's actual candidate set or a graph-visit count.

## Matched physical execution

Four stages, in order: 100k/build1, 250k/build1, 250k/build2, 100k/build2.
Every stage physically loads its scale and builds its own graph. The first
100k stage must pass independent verification and the manipulation/resource
gates before 250k starts. No 500k/1M authorization in this profile.
Retain the same source and implementation bytes throughout the matched stages.

Within each stage: 2 modes x3 methods x5 filters x200 queries x5 repetitions =
30,000 measured executions; 600 disjoint warmups; 30 actual prepared-plan
audits; 2,000 truth records plus full deterministic reexecution and 40 NumPy
spot checks. Total planned campaign: 120,000 measured calls, not independent
observations. Modes execute legacy then radial in build1 and reverse in build2.
Block order is deterministically hashed, reversed for build2; each repetition's
query order is shared across modes/methods/filters/scales within its build.

Use SIFT1M pinned HDF5 SHA256
`dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984`,
128D unnormalized float32, L2, k10. PostgreSQL17.11/pgvector0.8.6.
m16, ef_construction64, ef_search40; iterative strict_order, max_scan_tuples20000,
scan_mem_multiplier1. Exact work_mem4MB, ANN64MB, shared_buffers128MB, JIT off,
force_generic_plan, same recorded planner/parallel controls as preparation
study. Graph build maintenance_work_mem1GB, no parallel maintenance.

CHECKPOINT and verified shared-buffer eviction before each mode; OS cache is
retained. Twenty disjoint warmups per method/filter block, all five measured
passes retained. No steady-state or cold-OS-cache claim. Persistent method
sessions, serial execute+fetch timing, plan audit/scoring/persistence outside
timer. Incremental fsynced checkpoints between passes. AC power, advisory lock,
other-client boundary checks; at least2GiB reported available RAM and10GiB free
disk before loading. Host snapshots and load/index/truth/resource costs saved.
No tests/analysis jobs run during timed database work.

## Analysis and interpretation

Primary query-level unit: fixed query ID; repetitions are technical repeats.
Physical graph/run is the higher-level replication block, not independent
metadata realizations. Pair metadata contrasts on the same graph and report
each scale/build separately; scale contrasts have newly constructed graphs
and remaining time/order effects. Do not pool 120k calls as independent samples.

Report canonical and tie-aware Recall@10, returned-10 rate and mean returned
count, including ANN shortfalls. Exact must return10 with recall1. Primary
latency p50/p95 are across200 per-query five-repetition medians; separately
report each pass median and raw-request p95. Retain first/later and later-pass
drift diagnostics; small latency differences remain descriptive and uncertain.

At each fixed selectivity compare paired radial-minus-baseline query quality
and paired latency ratios. Report local density versus returned count/recall,
with descriptive rank association where nonconstant and counts grouped by
top40 qualifying neighbors (0,1–9,10+). Record filtered exact kth distance and
query-anchor distance as limited difficulty descriptors. Do not use these
observational relationships as identified graph-traversal causes or build an
adaptive selector. Negative/mixed effects do not trigger selective reruns.

## Validation and stop

Require pinned source bytes, exact physical source/metadata equality, cardinality,
dimensions, mode-specific truth/checksums, tie handling, actual generic plans
and predicates,1022 generic/0custom uses per statement, same physical graph
within modes, fresh physical identities between stages, settings continuity,
complete schedules/observations/chunk coverage, positive timings, resource
evidence and immutable terminal manifests. Offline reconstruction independently
checks metadata, truth samples, metrics, plans and grid. Preserve failures.

Complete the four matched stages only if earlier gates pass; analyze and
independently verify, commit evidence, then stop. A failed manipulation check or
genuine unresolvable validation/resource problem is a defensible checkpoint,
not an invitation to disguise failures. Later scales are a separate decision.

Limits: one anchor/metadata realization, synthetic block-balanced labeling,
one host/dataset, bounded ANN settings, few physical blocks, nested dependent
filters, residual timing/OS/thermal variation and unequal exact/ANN work_mem.
Quantitative association must be observed, not presumed from construction.

## Focused literature

[pgvector0.8.6](https://github.com/pgvector/pgvector/tree/v0.8.6) documents
post-index filtering and bounded iterative scanning. [ACORN](https://arxiv.org/abs/2403.04871)
already studies predicate-dependent hybrid vector search. These motivate
the contrast and prevent a novelty claim; this study does not implement ACORN
or claim to discover filtering dependence for the first time.
