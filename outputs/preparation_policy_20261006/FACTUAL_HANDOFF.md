# Filtered vector search: preparation-policy milestone handoff

6 October 2026. Factual research checkpoint, not polished A5 prose or final
multi-scale findings. The A5 PDF was not changed.

## Outcome and decision

The matched 100k campaign completed and passed independent correctness,
plan, provenance and artifact verification. Adding one exposure to all measured
queries did **not consistently resolve repetition-associated latency variation**.
Only exact search at 20% selectivity met the frozen two-metric directional rule
in both builds; it also met the stricter operational acceptance rule. None of
the ten ANN method/filter conditions met those rules. This is a negative/mixed
measurement-qualification result, not a failed database run.

All five measured repetitions remain in the primary analysis. No selective
rerun, added warmup, deleted observation, metadata change, or 250k+ execution
followed the result. Correctness infrastructure is ready for further work;
a final multi-scale latency campaign is not yet justified by an assumption of
stable timing. The next intervention requires a separate design checkpoint.

## Starting state, preservation and progression

Starting HEAD was `38baba3fbf4e84dfb83d0642fe7cc067fcb748f2` on `main`.
The existing project already had a corrected SIFT 10k preflight, physical 100k
qualification, and two full 100k rounds containing 30,000 measured executions.
Those were not rerun or relabeled as the new experiment.

Eleven prior uncommitted audit files were reviewed, including a repetition
diagnostic and 20 new tests. All 148 tests passed before adopting those files.
The unrelated formatting-only change to
`raw_results/milestone_2/20260915T184137Z_bf300f7b1133/failure.json`
was deliberately left uncommitted and byte-for-byte unchanged in the original
worktree. Its working SHA256 is
`3707e3624b10d59936c6d53de6d743e71b7346ba83f1359fdf207023d86f3e9b`;
the committed version is
`492635d51025cf3bb0b063bcf4474971a8f868b5df29d3e39e9d01631055d255`.
That known historical checksum exception is not a new corruption or silently
repaired evidence. All 322 starting evidence-file hashes in
`STARTING_STATE.json` still match the original worktree.

Implementation and execution were isolated on `research/preparation-policy`
in the sibling `filtered-vector-search-preparation` worktree. Ignored symlinks
reuse the existing Python environment and PostgreSQL/dataset runtime. The
original branch receives only fast-forward updates; no history is rewritten.
The project is named **Filtered vector search**, not the name of its parent
workspace folder. No filesystem relocation or provenance-path rewriting was
attempted in response to the unresolved naming clarification.

Chronological history:

| Date | Commit | Actual progression |
|---|---|---|
| Sep 15 | `cd199a2` | Verified synthetic Milestone 1 |
| Sep 15 | `61519cd`, `8682a76`, `8f537a4`, `0f5fe34` | Initial SIFT harness, version-gate corrections, first corrected preflight |
| Sep 29 | `97eb5b0`, `6708bfa` | Hardened harness and independent percentile-roundoff correction |
| Sep 29 | `8f62bb3` | Verified corrected 10k SIFT preflight |
| Sep 29 | `5549ad1`, `1b68328` | Preserved blocked qualification attempt; verified physical 100k qualification |
| Sep 29 | `5d6a16f`, `3692827` | Restart-verified full-round profile and qualification figures |
| Sep 29 | `e7952e5`, `f671005` | Full 100k rounds 1 and 2; independent pair verification |
| Sep 29 | `fa5a03f`, `38baba3` | Academic evidence and larger-scale review checkpoint |
| Oct 6 | `7dc2f81b9b2d38a8c2f8df886db67b2a39d6b266` | Adopted reviewed timing audit and tests |
| Oct 6 | `53d85243e4ddc2992e8ce679b9ac26913e1dfd93` | Frozen preparation-policy implementation, durability, tests and protocol |
| Oct 6 | `8f6f7a3dca6c3d92d8ac8bf16a77bb8ad1fb0cd4` | Source-linked historical timing reanalysis; source commit used for new run |
| Oct 6 | `378bc8b75595226f66de6ce397778dc5e455f8d5` | Independently verified new raw campaign and verification report |

The publishing commit adds the final analysis, reproducible arithmetic audit
and this handoff. Its exact hash is reported in the final user handoff and can
be retrieved with `git log -1 --format='%H %s'`; a document cannot include its
own Git commit hash without changing that hash. No remote push was performed.

## Why this milestone

Candidates were controlled metadata/neighborhood association, more physical
scales, offline reanalysis alone, and a matched preparation-policy experiment.
The last option was selected because latency validity affects every later
comparison. Correlation remains important instructor feedback, but another
experimental factor or a larger scale would not resolve the observed timing
uncertainty. Reanalysis and durable persistence directly support this one
measurement question rather than broadening the system.

Historical reanalysis confirmed:

- Standard HNSW, 50%, round 1 pass medians:
  17.902 / 1.966 / 1.621 / 1.617 / 1.572 ms.
- Median paired first/later latency exceeded 1.2 in 6/30 conditions and 2 in
  4/30. Later-pass median max/min exceeded 1.2 in 11/30.
- All 6,000 historical query/condition/build cells retained identical ordered
  results, distances and quality across repetitions.
- Every recorded prepared statement had 1,022 generic uses and zero custom
  uses. A generic/custom plan switch is not an evidenced explanation.
- Ten sampled exact plans used 25 kB in-memory top-N sorts, no temporary I/O,
  and no lossy bitmap blocks. Exact work_mem shortage is not demonstrated.
- The 20 warmups and 200 measured queries are disjoint but small unequal
  samples. Query descriptors are available; they do not prove equal difficulty.

These are observed/derived facts. Cache competition, host scheduling, thermal
effects and other mechanisms remain hypotheses. The old restart-based runs and
new eviction-based campaign are not matched comparison arms.

## Frozen experiment and actual execution

Question: does one complete measured-query exposure pass reduce first/later
discrepancy and later-pass variation, relative to 20 disjoint warmups, with
data, graph, settings and schedules matched within a build?

Hypothesis: both diagnostics improve in both builds without changing quality.
The protocol explicitly accepted a negative/mixed result as a stopping point.

- Run: `20261006T085044Z_5791f42860c1`.
- Source: clean `8f6f7a3dca6c3d92d8ac8bf16a77bb8ad1fb0cd4`.
- Config: `config/preparation-policy-v1.json`; canonical-JSON config SHA256
  `5791f42860c160a24ba0f32b40b2a9682c14ba45dcb133bb36627d3589ca06c8`.
  The source file's byte SHA256 is
  `4bd594f97c58eed24683ba334d953bdb16955fa63830a390e5df91dfc790aa1c`;
  whitespace is excluded by canonical config hashing, not by file hashing.
- PostgreSQL 17.11 (Postgres.app), pgvector 0.8.6; Python 3.12.0.
- SIFT1M ANN-Benchmarks HDF5: SHA256
  `dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984`.
  128D float32, L2, no normalization.
- Two physical 100,000-row loads, each with its own HNSW graph. Six relation
  OIDs/filenodes change between builds and remain fixed within paired arms.
- Selection is deterministic SHA256 ID ranking, not newly sampled vectors.
  Metadata is `scale_rank % 100`, without consulting vector values.
  Filters `filter_bucket < 50/20/10/5/1` qualify exactly
  50,000/20,000/10,000/5,000/1,000 rows. These filters nest.
  Content-blind assignment is not proof of statistical independence from geometry.
- 200 fixed measured queries, 20 disjoint warmups, k=10, five retained
  repetitions, exact/standard HNSW/strict-order iterative HNSW.
- HNSW m=16, ef_construction=64, ef_search=40; iterative strict_order,
  max_scan_tuples=20000, scan_mem_multiplier=1.
- Exact work_mem=4 MB; ANN=64 MB; shared_buffers=128 MB; JIT off;
  force_generic_plan; fixed planner and parallel controls. This is a configured
  system comparison, not equal-memory algorithms.
- A: 20 disjoint warmups per method/filter block.
  B: those same 20 plus all 200 measured-query exposures before measurement.
  Build 1 order A/B; build 2 B/A. Within-build block/query schedules match;
  block order reverses between builds.
- CHECKPOINT plus verified shared-buffer eviction before each arm. This is
  neither a restart nor an OS-cache flush. Plan probes use a disjoint warmup
  query before block preparation. New persistent method sessions per arm.
- Exactly 60,000 measured calls, 7,200 separately recorded preparation calls,
  60 plan audits involving 120 probe executions. No other database client was
  observed at the 11 guarded boundaries; this is not continuous host isolation.

The schema remains two identical-row tables:
`milestone2.sift_exact` and `milestone2.sift_hnsw`, each containing
`id integer PRIMARY KEY`, `scale_rank integer NOT NULL`,
`filter_bucket smallint NOT NULL`, and `embedding vector(128) NOT NULL`.
Only the exact table has a metadata B-tree; only the ANN table has HNSW.

The single-bound-vector SQL remains:

```sql
-- threshold shown as 50; separate prepared statements use 20, 10, 5 and 1.
SELECT id, embedding <-> $1::vector AS distance
FROM milestone2.sift_exact
WHERE filter_bucket < 50 ORDER BY distance, id LIMIT 10;

-- Both ANN methods use this same SQL with their own session settings.
SELECT id, embedding <-> $1::vector AS distance
FROM milestone2.sift_hnsw
WHERE filter_bucket < 50 ORDER BY distance LIMIT 10;
```

Ground truth uses exact filtered distances including all kth-boundary ties,
then deterministic distance/ID canonical ordering. It is generated and
reexecuted for all 1,000 query/filter cells in each build, with 20 independent
NumPy checks per build. The performance baseline permits the planner to use
sequential/parallel/metadata-index paths on the table without a vector index.
This is different from Milestone 1's forced sequential correctness path.

## Measurement and analysis definitions

The treatment unit is an arm execution: four arms in two graph/order blocks.
The 200 query IDs are paired subsamples and five repetitions are technical
repeats. Neither 60,000 executions nor two rebuilt graphs constitute a large
independent sample. Selectivities and query difficulty are dependent.

Latency is client `perf_counter_ns` around prepared execute + fetch of the
same results scored for recall. Setup, EXPLAIN, scoring, serialization and
journal persistence are outside the timer. Primary median is the median of
200 per-query medians over all five repetitions. The corresponding p95 is a
query-median p95, not request-tail p95. Individual-request p95 is also reported
separately within every pass. No cross-build latency pooling or significance
test is used.

Canonical Recall@10 = intersection of returned IDs and canonical exact top-10
IDs, divided by 10. Missing rows reduce recall. Tie-aware recall credits required
strictly closer IDs plus up to the remaining slots from the kth-distance tie
set. Returned-10 rate and mean returned count are separate from recall.

Stability diagnostics are median paired first/later ratio, median absolute
log2 of that ratio, and max/min of pass medians 2–5. A predeclared engineering
flag checks whether any pass median divided by the median of per-query later-
four medians is outside [0.8,1.2]. It is not a statistical test or proof of
steady state. The strict directional rule requires B to reduce both absolute-
log2 discrepancy and later-pass range in both builds, with stable quality.
Operational acceptance also requires no B engineering flag in either build.

## New results: validation evidence, not final findings

| Build / arm | Flagged method/filter conditions out of 15 | Disjoint warmup query seconds | Extra exposure query seconds |
|---|---:|---:|---:|
| 1 / A | 3 | 3.225 | none |
| 1 / B | 4 | 2.061 | 17.729 |
| 2 / A | 4 | 2.497 | none |
| 2 / B | 0 | 4.821 | 19.758 |

The zero flags in build 2/B do not erase the four flags in build 1/B.
Only exact/20% meets both-build directional and operational criteria (1/15
method/filter conditions). Its absolute-log2 diagnostic decreases
0.11870→0.10014 and 0.07344→0.06616; later-pass range decreases
1.06185→1.02961 and 1.18359→1.03218. These are small descriptive effects, not
a statistically established benefit.

A useful counterexample is standard HNSW/10%:

| Build / arm | Five pass medians, ms | Median paired first/later | Later max/min |
|---|---|---:|---:|
| 1 / A | 5.924, 1.204, 1.171, 1.170, 1.157 | 5.025 | 1.041 |
| 1 / B | 1.171, 1.124, 1.083, 1.131, 1.018 | 1.026 | 1.112 |
| 2 / A | 1.157, 1.015, 1.149, 1.211, 1.121 | 0.997 | 1.193 |
| 2 / B | 1.156, 1.136, 1.096, 1.259, 1.230 | 0.974 | 1.149 |

The first-build first-pass anomaly is reduced, but later spread worsens; the
same first-pass anomaly is absent in build 2/A. A blanket claim that additional
warmup fixes the issue is unsupported.

All 12,000 within-arm query cells and all 6,000 paired across-arm query cells
retain identical ordered IDs, distances, recall and completeness. This does
not require identical ANN results across separately rebuilt graphs.

Selected absolute measurements below are descriptive context from Arm A only,
not a policy comparison or a final algorithm ranking:

| Method / filter | Build 1 / 2 primary median ms | Build 1 / 2 canonical Recall@10 | Returned 10, both builds |
|---|---:|---:|---:|
| exact / 50% | 21.148 / 22.800 | 1 / 1 | 100% |
| standard / 50% | 0.971 / 1.182 | 0.965 / 0.964 | 99.5% |
| iterative / 50% | 1.105 / 1.375 | 0.965 / 0.964 | 100% |
| exact / 1% | 1.343 / 1.689 | 1 / 1 | 100% |
| standard / 1% | 1.072 / 1.160 | 0.042 / 0.042 | 0% |
| iterative / 1% | 11.160 / 10.194 | 0.983 / 0.983 | 100% |

Standard/1% returns 0.42 rows on average, not zero for every query.
Iterative/50% tie-aware recall is 0.9655/0.9645. All 60 conditions, all four
arms, per-pass p95s, quality values and paired ratios are in
`pilot_analysis/ANALYSIS.md` and `analysis.json`; none are suppressed here.

## Live plan evidence and resource observations

All 60 probes execute the actual generic prepared statement. Exact/50%
uses Limit → Gather Merge → Sort → parallel sequential scan. Exact/20%
uses Limit → Sort → Bitmap Heap Scan → Bitmap Index Scan on
`sift_exact_filter_bucket_idx`. All ANN probes use
`sift_hnsw_embedding_idx` beneath Limit; no unintended pre-limit sort,
metadata B-tree or unrelated HNSW path is accepted.

Representative build 1/A, disjoint query 3454, 1% filter:

- Standard HNSW: Index Scan, 0 returned, 40 removed by filter;
  saved server Execution Time 0.671 ms. Raw plan:
  `plans/b1_A_be00a4b9890c9fb728b7.json`.
- Iterative HNSW: Index Scan, 10 returned, 1,089 removed by filter;
  raw plan `plans/b1_A_4e07e585b5f45b79c981.json`.

These instrumented probe times are not the primary client timings.
Prepared statements end with exactly 1,022 generic uses in A or 1,222 in B,
zero custom uses, and unchanged effective method settings.

| Phase | Build 1 seconds | Build 2 seconds |
|---|---:|---:|
| COPY source into exact table | 4.157 | 5.081 |
| COPY exact table into ANN table | 1.918 | 1.720 |
| Exact metadata index | 0.104 | 0.086 |
| HNSW graph build | 65.026 | 77.516 |
| Ground-truth generation | 11.594 | 14.159 |
| Deterministic truth reexecution | 11.457 | 13.877 |
| Producer NumPy spot validation | 1.044 | 0.816 |
| Vacuum/analyze/checkpoint | 0.983 | 2.548 |

Actual run interval: 08:50:44.154941–09:03:16.915268 UTC, about 12m33s.
Measured query-call time sums to 307.372 seconds; preparation calls sum to
50.092 seconds. Neither is whole-workflow elapsed time.
HNSW construction uses maintenance_work_mem=1 GB, no parallel maintenance.

Exact heap is 56 MiB; ANN heap 55.805 MiB; HNSW index 79.258/79.297 MiB.
Total relations including each table's indexes are about 196.95/196.98 MiB.
Do not add index sizes again to pg_total_relation_size.
390 boundary snapshots show 16 GiB host RAM, 3.604–7.019 GiB available,
32.910–36.047 GiB free disk, and runner lifetime maximum RSS 452.258 MiB.
The Python process reports x86_64/macOS; PostgreSQL's inspected build is
aarch64. Logical CPU count is unavailable; recorded physical count is 4.
Do not silently characterize this as one uniformly native execution environment.
AC power was checked before/after.

RSS is not PostgreSQL peak memory. The snapshots do not establish thermal,
swap, physical-disk-I/O, or background-process causes. Raw artifacts occupy
approximately 150 MiB (including consolidated rows and durable chunks); the
largest file is approximately 65 MiB. No new larger-scale cost projection is
claimed: linear extrapolation from this single-scale timing is not validated.

## Validation, implementation fixes and reproducibility

Independent verifier: passed, 511 payload files plus manifest/terminal marker,
60,000 measured calls, 7,200 preparations, 2,000 ground truths, 60 plans,
40 fresh NumPy checks, and source-distance checks over 67,260 query-result records.
Input checksums remained unchanged. Its independence is bounded: recall,
grids, artifact/provenance checks are independently reconstructed, while
source-selection, plan and NumPy helper code is shared and disclosed.

The separate NumPy/stdlib arithmetic checker imports no project analysis
helpers. It matched 1,785 condition/comparison/support/preparation fields
within 1e-12, with zero discrepancies. It explicitly derives operational
acceptance rather than confusing that with directional support.
All three new figures and both historical figures were visually inspected.

Tests: 148 baseline tests passed in 13.848s; 213 implementation tests passed
in 42.497s; the final complete run passed **213 tests in 45.326s**.
The 65 new tests cover frozen profiles/schedules, journaling/interruption,
session/identity gates, verifier mutations and analysis arithmetic/rendering.
AST checks passed for 12 new package/analysis/test files; the independent
arithmetic checker was also executed successfully. Dependency, shell syntax
and whitespace checks passed. Nonfatal font-cache/Matplotlib/pyparsing and
pip-cache warnings are not benchmark failures. The test log's bad-source
INVALID message is an intentional temporary fixture, not a failed live run.
An auxiliary `shasum` command encountered the host's unsupported `C.UTF-8`
Perl locale; rerunning with `LC_ALL=C` passed and confirmed the config byte hash.

Real implementation issues corrected before execution:

- A verifier expected only two nonfinite-count keys, while legacy database
  evidence includes a description. It now checks the two required counts;
  a regression uses the real saved schema.
- A test fixture shadowed unittest.TestCase.run; it was renamed.
- Cross-arm quality equality alone could hide matching changes within both
  arms. The support gate now checks repetition-level stability too.
- Review found a chunk filename-prefix mismatch; it was fixed before the run.
- The sandbox could not attach PostgreSQL shared memory. The operator started
  the existing cluster from Terminal; no arm-by-arm restarts were needed.

The new runner writes exclusive fsynced preparation/pass chunks. A caught
interruption saves the active completed-row prefix; an uncatchable kill may
lose the active batch. This mitigates the legacy runner's end-of-workload
buffering without altering historical evidence. Checksums provide alteration
detection, not physically write-protected storage. No real new campaign failed.

Exact principal commands, from the preparation worktree (the operator's server
start was from the original project directory):

```bash
./scripts/postgres_local.sh start
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.preparation.runner --config config/preparation-policy-v1.json
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.preparation.verify raw_results/preparation_policy/20261006T085044Z_5791f42860c1
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m analysis.preparation_policy pilot raw_results/preparation_policy/20261006T085044Z_5791f42860c1 --output outputs/preparation_policy_20261006/pilot_analysis
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python outputs/preparation_policy_20261006/independent_arithmetic_check.py
.venv-milestone2/bin/python -m pip check
for script in scripts/*.sh; do bash -n "$script" || exit; done
git diff --check
```

These document commands actually run, not instructions to overwrite the saved
analysis directory. For reproduction use a NEW output directory; the runner
creates a new run ID and reloads the benchmark tables. Offline verification
and the arithmetic checker are safe read-only video demonstrations.
Check this handoff bundle from the repository root with
`LC_ALL=C shasum -a 256 -c outputs/preparation_policy_20261006/HANDOFF_CHECKSUMS.sha256`.
The historical reanalysis and full-pair verification commands are in
`docs/PREPARATION_POLICY_PROTOCOL.md` and `IMPLEMENTATION_CHECKPOINT.md`.

## Files and strongest evidence

All paths in this section are relative to the project root; the publishing
handoff supplies clickable absolute paths. `CHANGE_INVENTORY.txt` contains
the full added/modified file inventory since the starting commit.

- `experiments/preparation/protocol.py`, `config/preparation-policy-v1.json`:
  strict 100k-only frozen design, deterministic schedules and settings.
- `experiments/preparation/runner.py`: two physical graphs, AB/BA execution,
  persistent sessions, controls, plan audits and terminal evidence.
- `experiments/preparation/journal.py`: durable exclusive batch persistence.
- `experiments/preparation/verify.py`: offline artifact/grid/truth/source checks.
- `tests/preparation/`: five focused test modules and package initializer.
- `analysis/preparation_policy.py`: historical and matched-arm summaries,
  immutable-by-workflow derived artifacts, three pilot/two historical figures.
- `docs/PREPARATION_POLICY_PROTOCOL.md`: hypothesis, design, units, limits,
  primary-source rationale, frozen decision criteria and reproduction commands.
- `raw_results/preparation_policy/20261006T085044Z_5791f42860c1/`:
  513 raw files, including 390 chunks, consolidated observations, two builds'
  truths/identities/metrics, four arms' controls, 60 plans, manifests and logs.
- `outputs/preparation_policy_20261006/PILOT_VERIFICATION.json`:
  independently obtained raw-run verification result.
- `outputs/preparation_policy_20261006/pilot_analysis/`: complete table,
  machine-readable analysis, three figures and integrity manifests.
- `outputs/preparation_policy_20261006/historical_analysis/`: separate,
  non-comparative historical context and query descriptors.
- `outputs/preparation_policy_20261006/independent_arithmetic_check.py` and
  `INDEPENDENT_ARITHMETIC_CHECK.json`: reproducible independent reductions,
  operational decision and resource summaries.
- `STARTING_STATE.json`, `IMPLEMENTATION_CHECKPOINT.md`, this handoff and
  `HANDOFF_CHECKSUMS.sha256`: preservation, dated progress and final evidence.
- README now points to this completed milestone; .gitignore supports ignored
  runtime/environment symlinks. Earlier audit additions were adopted, not
  silently represented as newly invented work.

## A5 corrections and a 3–5 minute demonstration

Do not replace the draft PDF without a separate request. Required factual
corrections to the provided draft:

1. Pages 5–6: replace claims of metadata independence/no geometric correlation
   with content-blind deterministic rank-modulo assignment; association is
   unmeasured. Cluster-correlated conditions remain unfinished.
2. Pages 2, 4 and 6: executing warmups does not establish steady-state timing.
   Add the historical drift and this completed negative/mixed policy test.
3. Pages 3–4: define the median of per-query medians, canonical versus tie-aware
   recall, and technical repetitions. Do not call 30,000 or 60,000 independent
   observations, or pool rebuilt graphs without a defined estimand.
4. Page 7: preserve old 100k runs as their own exploratory protocol. Changed
   semantics require matched reference runs before final scale comparisons.
5. Pages 3/6: distinguish 128 tests at the September checkpoint, 148 at the
   earlier October audit, and 213 after this implementation. Date each claim.
6. Include exact work_mem=4 MB versus ANN=64 MB; there is no demonstrated exact
   spill in sampled plans, but no equal-resource comparison claim either.
7. Explain checksum-based immutability and the preserved historical formatting
   exception; do not imply write-once storage or zero-loss crash durability.
8. Add the corrected Sep 29 preflight commit `8f62bb3`, not only Sep 15
   `0f5fe34`. Correct figure numbering that jumps from 1 to 3; avoid the
   one-row table split and label shortened SQL excerpts as excerpts.
9. Do not infer being behind schedule solely from incomplete scales: the
   approved proposal had no strict week-by-week deadlines.
10. Retain all seven cumulative rubric sections; add this milestone only with
    its actual Oct 6 date and confirm eligibility under the Week 7 cutoff.
    The Canvas deadline was reported as Oct 6 at 14:30; its display timezone
    was not independently verified. No video or submission was created here.

Suggested live demonstration, using actual files rather than slides only:

- 0:00–0:35: README research question and the exact/ANN SQL in
  `experiments/milestone2/database.py` (`search_sql`, `timed_execute_fetch`).
- 0:35–1:15: `docs/PREPARATION_POLICY_PROTOCOL.md`: two graphs, AB/BA,
  same queries, all five repetitions; explain what changes and what is held.
- 1:15–2:00: terminal output of the offline verifier and
  `PILOT_VERIFICATION.json`; show one exact and one ANN raw plan.
- 2:00–3:00: `pilot_analysis/first_later_deviation.png` beside
  `later_pass_spread.png`; show why fixing one first pass does not establish
  later stability. These are generated figures, not screenshots.
- 3:00–4:00: `pilot_analysis/ANALYSIS.md` and
  `INDEPENDENT_ARITHMETIC_CHECK.json`: 1/15 accepted conditions, unchanged
  quality, mixed latency and preparation cost.
- 4:00–4:40: Git history plus this handoff's limitations/next milestone.
  No new benchmark run is needed for the video.

No new screen recording or screenshots were fabricated. The best source-linked
figures and exact plan files above are ready to display or capture.

## Claims, limitations, next milestone and ownership

OBSERVED FACT: the new physical campaign completed with the saved plan paths
and result grid. DERIVED RESULT: the frozen support/acceptance criteria hold
only for exact/20%, with all 1,785 independently recomputed fields agreeing.
IMPLEMENTATION GUARANTEE: source/profile and evidence gates reject the tested
invalid states; this is not proof against every possible bug.

INFERENCE: one measured-query exposure is insufficient to adopt as a general
stability remedy on this workload/host. HYPOTHESIS: cache competition, system
scheduling, thermal state or order effects contribute. ASSUMPTION: remaining
unobserved host activity is not systematically favorable to a particular arm;
AB/BA only partially addresses this with two blocks.

LIMITATIONS: one host, dataset, physical scale and ef_search setting; four arm
executions; synthetic metadata; no measured local geometric association;
OS cache retained; generic-plan/preparation and parallelism-specific workload;
unequal exact/ANN work_mem; instrumentation limited to boundary snapshots and
representative plans; no dedicated host, temperature or physical-I/O traces.
B changes both total prior work and query familiarity. Journaling between passes
can affect following state even though it is outside the timer. Two graph
rebuilds do not estimate a population distribution of graph outcomes.

UNSUPPORTED CLAIMS: a proven cache cause, universal warmup fix, final
multi-scale recall/latency law, statistically significant method superiority,
new ANN novelty, or guaranteed reproducible timing. Primary literature already
overlaps filtered ANN, predicate/vector relationships and planner behavior;
the focused links in the protocol bound rather than establish novelty.

The strongest next distinct milestone is a bounded timing-mechanism and
measurement-policy decision, not more rows. On a quiet, documented host,
freeze repeated time blocks and low-overhead host/PG diagnostics, distinguish
first-touch from later drift, and decide whether to estimate a specified
operational workload distribution rather than claim steady state. If testing
query familiarity specifically, add an equal-work disjoint-query control.
Choose the design before inspecting new timings; do not tune warmups until
the same data pass. A literature/novelty checkpoint and the metadata-neighborhood
association design should precede the eventual matched larger-scale campaign.

Questions the student should be able to answer:

- Why does PostgreSQL postfiltering make standard HNSW return fewer than k?
  Why is strict iterative order still approximate, and how is scan effort bounded?
- Why are correctness ground truth and a realistic exact-performance baseline
  different jobs? Why can the exact planner use a metadata B-tree?
- Why bind the query vector once, and how does the actual prepared plan prove
  HNSW execution rather than merely index existence?
- Why are completeness, canonical recall and tie-aware recall different?
- What exactly is inside the latency timer, and why is EXPLAIN not that timer?
- What is the treatment unit? Why is query-median p95 not request p95?
- What does shared-buffer eviction reset, and what does it leave uncontrolled?
- Why can the new experiment be valid even when the proposed remedy fails?
- Why does a content-blind metadata generator not prove independence?
- What does a checksum detect, and what evidence can still be lost on a hard kill?

Stop here. No automatic further experiment, larger scale, A5 edit or publication.
