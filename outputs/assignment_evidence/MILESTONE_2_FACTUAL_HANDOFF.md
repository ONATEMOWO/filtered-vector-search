# Milestone 2 factual handoff

Date: 29 September 2026. Qualification observations are not final research
findings. The research question is unchanged. Corrected 10k, bounded 100k,
and both standalone full-100k rounds are complete and independently verified.
The last run-artifact commit is `f67100500bbfcc09bf7ccd3b1e42dd8e344fc801`;
the containing documentation commit packages this final handoff.

## Starting state and preservation

The starting HEAD was `0f5fe348813934e9f93ccb483be2979feac59d8c`, containing the
historical corrected 10k preflight from 15 September. Sixteen files were
modified but uncommitted. The newest strict checks were not green, and no 100k
qualification had run. The exact files and Git history were archived before
editing; no reset, discard or reconstruction was used. The preserved changes
were inspected, reconciled with the protocol and included in the corrected
harness commit. See `CHECKS_AND_COMMANDS.md` for preservation paths and hashes.

Milestone 1 and all three historical Milestone 2 run directories remain
unchanged. Historical 10k evidence is retained for provenance but superseded
by the new single-vector/prepared-plan-verified preflight. It is not pooled
with the new results.

## Project structure and important files

```text
config/milestone2/             frozen protocol and exact stage profiles
sql/milestone2/                separate tables, metadata B-tree, HNSW index, SQL examples
data/sift1m/source_manifest.json canonical source URL/size/checksum
scripts/acquire_sift1m.py       acquisition and validation entry point
experiments/milestone2/
  config.py                   scope/count/settings gates
  dataset.py                  source validation and deterministic selections
  database.py                 physical loading, evidence, sessions, same-query timer
  ground_truth.py             durable exact truth, ties, NumPy cross-checks
  metrics.py                  recall, completeness and row validity
  plans.py                    actual prepared-generic EXPLAIN audits
  artifacts.py                exclusive writes and immutable terminal states
  runner.py                   one physical run and complete artifact lifecycle
  restart.py                  full-run real restart and physical-identity proof
tests/milestone2/              unit/tamper regressions and independent run/pair verifier
raw_results/milestone_2/       immutable successful and invalid runs
analysis/generate_assignment_figures.py  source-linked descriptive qualification plots
outputs/assignment_evidence/   A3/A4, current state, figures, tables and handoff
```

The large dataset, virtual environment, PostgreSQL binaries/data, generated
scale-order cache and plotting cache are ignored runtime files, not Git data.
The complete changed-file inventory is provided separately in this bundle.

## Verified environment, data and schema

- PostgreSQL **17.11** (`17.11 (Postgres.app)`, numeric version `170011`),
  pgvector **0.8.6** installed and active; database `filtered_vector_search`,
  user `temz`, TCP `127.0.0.1:55432`.
- Local macOS 15.0, x86_64, 16 GiB RAM, four physical CPU cores reported.
  Logical CPU count was unavailable in the recorded environment; no value is
  invented. Docker was absent; the existing project-local PostgreSQL runtime
  was retained rather than replacing the environment.
- Python 3.12.0; h5py 3.14.0, NumPy 2.2.6, Python pgvector 0.4.1,
  psycopg/psycopg-binary 3.2.9, psutil 7.0.0. Optional figure library:
  matplotlib 3.10.0. Exact requirements are version controlled.
- Source: `https://ann-benchmarks.com/sift-128-euclidean.hdf5`, 525,128,288 bytes,
  SHA256 `dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984`.
  `train` is 1,000,000×128 float32; `test` is 10,000×128 float32;
  supplied neighbors are 10,000×100 int32. Shapes, dtypes, finite values,
  zero-based ID ranges and Euclidean attribute were validated. No values
  were normalized. Supplied unfiltered neighbors were not used as filtered truth.

Both `milestone2.sift_exact` and `milestone2.sift_hnsw` have:

```sql
id integer PRIMARY KEY CHECK (id >= 0),
scale_rank integer NOT NULL CHECK (scale_rank >= 0),
filter_bucket smallint NOT NULL CHECK (filter_bucket BETWEEN 0 AND 99),
embedding vector(128) NOT NULL
```

Exact has a B-tree on `filter_bucket` and no vector index. HNSW has
`sift_hnsw_embedding_idx USING hnsw (embedding vector_l2_ops)
WITH (m=16, ef_construction=64)` and no metadata B-tree. Rank uniqueness and
range are checked without adding another HNSW-table B-tree. The two tables
are checked row-for-row and by ordered ID/rank/bucket/vector-byte checksum,
also compared with every selected original source vector. Statistics target
is 1,000; vacuum/analyze/freeze and checkpoint precede measurement preparation.

SIFT selection uses no synthetic-vector seed: IDs are globally sorted by
SHA256(`sift-base-v1|` + decimal ID), with ID as tie-break. Each physical scale
is a prefix, not a predicate over a larger graph. Metadata is synthetic:
`filter_bucket = scale_rank % 100`. The global int32 order digest is
`5fff299d2950d88779871ffa4b21660c51d295c44f09ffbee82bac7f164b1fc9`.
Query IDs are sorted using the separate `sift-query-v1|` domain; the first
200 are measured queries and the next 20 are disjoint warm-ups.

| Physical scale | 50% | 20% | 10% | 5% | 1% |
|---:|---:|---:|---:|---:|---:|
| 10,000 | 5,000 | 2,000 | 1,000 | 500 | 100 |
| 100,000 | 50,000 | 20,000 | 10,000 | 5,000 | 1,000 |

## SQL, settings and correctness

Exact workload SQL (the literal threshold ranges over 50, 20, 10, 5, 1):

```sql
SELECT id, embedding <-> $1::vector AS distance
FROM milestone2.sift_exact
WHERE filter_bucket < 50
ORDER BY distance, id LIMIT 10;
```

Both HNSW methods use this single-parameter workload SQL:

```sql
SELECT id, embedding <-> $1::vector AS distance
FROM milestone2.sift_hnsw
WHERE filter_bucket < 50
ORDER BY distance LIMIT 10;
```

All method sessions use `jit=off`, `statement_timeout=120s`, and
`plan_cache_mode=force_generic_plan`. Exact keeps sequential, bitmap, index
and index-only scan paths enabled, with PostgreSQL's natural planner choice.
Both HNSW connections use `work_mem=64MB`, `enable_seqscan=off`,
`enable_bitmapscan=off`, `hnsw.ef_search=40`, `hnsw.max_scan_tuples=20000`,
and `hnsw.scan_mem_multiplier=1`. Iterative mode is `off` for standard and
`strict_order` for iterative. Index construction uses `maintenance_work_mem=1GB`
and zero parallel maintenance workers; no parameter sweep was performed.

Ground truth is calculated before timing on the exact-only table using
distance ordering and `FETCH FIRST 10 ROWS WITH TIES`. Canonical IDs are the
first ten after `(distance, id)` ordering. Strictly closer and boundary-tied
ID sets are retained. All 1,000 combinations are re-executed identically;
20 deterministic combinations (four per filter) are independently checked
with NumPy, and that independent check is repeated by the read-only verifier.

Canonical Recall@10 is `|returned IDs ∩ canonical exact IDs| / 10`.
Tie-aware recall is `(|returned ∩ C| + min(10 - |C|, |returned ∩ T|)) / 10`,
where C is strictly closer IDs and T is the boundary-tie set. Missing results
reduce recall. Returned count, returning-ten flag and shortfall are separate.
IDs must be unique, in-scale, filter-valid and sorted by finite nonnegative
L2 distance. Exact timed results must be complete and have recall one.

## Timing, preparation and actual plans

One query runs at a time over persistent driver connections. Statements are
prepared in the untimed plan-audit phase and reused. `perf_counter_ns()` starts
immediately before prepared `execute` and stops after `fetchall` for the same
IDs that are scored. Connection creation, session setup, query-vector selection,
preparation, scoring, artifact serialization and warm-up are outside that
interval. Raw integer nanoseconds are retained. Client/network/driver fetch
cost is included; EXPLAIN's execution time is not the benchmark latency.

Plan audits execute `EXPLAIN (ANALYZE, BUFFERS, SETTINGS, TIMING OFF,
SUMMARY ON, FORMAT JSON) EXECUTE` on the actual driver's prepared generic
statement. They retain its SQL, `{vector}` parameter type and before/after
generic/custom-plan counters. Routing, distance order, filter placement,
settings and actual row counts are asserted. These are 15 representative
audits per run, not an EXPLAIN inside each timed call.

Representative **100k qualification** plan evidence:

| Method/filter | Observed plan | Returned | Post-filtered at HNSW scan |
|---|---|---:|---:|
| Exact 50% | Limit → Gather Merge → Sort → parallel sequential scan | 10 | not applicable |
| Exact 1% | Limit → Sort → Bitmap Heap/Index Scan on metadata B-tree | 10 | not applicable |
| Standard HNSW 50% | Limit → HNSW Index Scan | 10 | 8 |
| Standard HNSW 1% | Limit → HNSW Index Scan | 0 | 40 |
| Iterative HNSW 50% | Limit → HNSW Index Scan | 10 | 8 |
| Iterative HNSW 1% | Limit → HNSW Index Scan | 10 | 1,044 |

Raw documents are in the qualification run's `plans/`; assertions identify
each corresponding JSON filename. Empty standard-HNSW results are legitimate
measured incompleteness, not discarded query failures.

## Qualification outcomes and resource evidence

Corrected preflight `20260929T165442Z_3a1810512444` passed: 10k rows per table,
5 measured queries × one repetition × 15 conditions = 75 measurements.
Bounded qualification `20260929T165921Z_bcce4b4163d7` passed: physically loaded
100k rows per table and a new graph, 20 queries × two repetitions × 15 = 600.
Both retained 1,000 exact truths and re-executions, 20 fresh independent checks,
300 warm-ups and 15 valid plans, with zero execution errors. Independent
verification left every payload checksum unchanged.

See `VERIFIED_MEASUREMENTS.md` for all 30 qualification condition summaries
and the three provenance-linked PNG figures. At 100k, exact-table copy was
6.240 s, copy to HNSW was 2.624 s, graph construction 99.187 s, initial ground
truth 15.291 s, ground-truth re-execution 16.375 s, and total before final
artifacts 172.135 s. HNSW index size was 83,132,416 bytes; table/index relation
bytes summed to 206,438,400. Successful 10k and 100k artifact directories were
1,880,518 and 2,546,916 bytes respectively.

100k qualification phase snapshots observed at least 2,935,885,824 bytes
available host memory and 33,338,793,984 bytes free disk. Client-process
maximum RSS reached 410,193,920 bytes on macOS. These are not continuous
PostgreSQL peak-RAM measurements; host memory/disk changes include other OS
activity. AC power was present at both boundaries with unchanged energy settings.

The recorded mechanical larger-study projection is 6,765.79 seconds
(112.76 minutes), 164,668,856 artifact bytes, and 2,064,384,000 relation bytes
at 1M. It linearly scales setup/storage and holds observed query latency fixed.
It excludes nonlinear graph/search growth, cache/thermal effects, WAL and
general host-disk changes, so it is neither a bound nor evidence that 1M is safe.

## Full 100k campaign

Final status and paired verification are recorded in `CURRENT_RESEARCH_STATE.md`.
This is the separate `standalone-100k-v1` campaign authorized by the resumed
request, not the original ascending/descending four-scale campaign.
Each full round has 15,000 timings, all 200 queries, five repetitions,
300 warm-ups, 1,000 ground truths/re-executions, 20 independent checks and
15 plans. Each loads a new physical scale and graph and requires an actual
postmaster restart with the same cluster and physical objects across restart.
Round-pair verification requires different physical objects between rounds.
No qualification cache-reset fallback is accepted for full rounds.

Both rounds passed independently and as a pair: **30,000 measured executions**,
600 warm-ups, 30 plan audits and two complete sets of 1,000 ground truths and
re-executions. The pair verifier performed 40 fresh NumPy checks. Exact results
were complete with canonical/tie-aware recall one; no execution or plan errors
were recorded. All scored results, source distances, schedules, checksums and
summary calculations passed. The two source commits had identical experiment
code/configuration despite an intervening artifact commit.

| Item | Full round 1 | Full round 2 |
|---|---|---|
| Run ID | `20260929T171847Z_f9d4cdb50ba7` | `20260929T172504Z_fa89b474a1c4` |
| Artifact commit | `e7952e5` | `f671005` |
| Exact / HNSW table copy | 5.969 / 3.936 s | 6.457 / 2.427 s |
| New HNSW graph build | 88.180 s | 87.150 s |
| Initial ground truth / re-execution | 13.966 / 13.249 s | 13.507 / 13.383 s |
| Workload plus warm-ups | 116.356 s | 117.213 s |
| Total before final artifacts | 290.482 s | 317.749 s |
| Included operator restart wait | 32.639 s | 61.384 s |
| HNSW index OID / file identifier | 24649 / 24649 | 24677 / 24677 |
| Immutable directory bytes | 20,704,241 | 20,703,894 |
| Minimum sampled available host RAM | 2,924,490,752 bytes | 2,854,346,752 bytes |
| Minimum sampled free disk | 32,236,519,424 bytes | 32,196,947,968 bytes |
| Client-process maximum RSS | 424,837,120 bytes | 410,820,608 bytes |

The shared ordered source/table stream digest is
`3ce8c350c501d1dc5267ffb44a1f11e276e2e80a22634d161df12f8c64e3b16e`.
The full pair proof is `FULL_100K_PAIR_VERIFICATION.json`; all condition
measurements, preserving build identity, are in `FULL_100K_MEASUREMENTS.md`.
The full-round mechanical larger-matrix projections are 95.39 and 94.37
minutes, distinct from qualification's 112.76-minute estimate. This variation
is another reason not to treat any projection as a guarantee.

The final complete unit suite passed **128 tests**. Compilation, dependency,
shell syntax and whitespace checks passed. Milestone 1 live checks and its
250-row historical-result validator passed again after both full runs.
Exact commands and independent-verifier outcomes are in `CHECKS_AND_COMMANDS.md`.

## Resolved defects, limitations and next checkpoint

Resolved: missing strict preflight profile field; two-bound-vector query and
unprepared/custom-plan audit ambiguity; unsafe checksum removal on attempted
re-finalization; independent p95 interpolation's one-nanosecond roundoff;
loopback permission denial before the first 100k load; and clipped shared-axis
latency bars in an initial rejected figure render. Failed benchmark evidence
and rejected derived renders were preserved, not silently replaced.

Qualification uses documented post-checkpoint shared-buffer eviction, verified
empty; full rounds use real restarts. Neither flushes the OS cache or claims
perfectly cold/warm caches. All blocks have the fixed 20-query warm-up.
The initial HNSW builds are stochastic; deterministic data/order and serial
construction do not guarantee identical approximate graphs. Two rebuilds
measure only a small part of that variability. Power is sampled at boundaries,
not continuously. This is a shared laptop, not an isolated benchmark host.

Metadata is synthetic and independent of vector content, not semantic filters.
One public dataset, one host, fixed HNSW settings and 100k-only full execution
cannot establish general scaling conclusions. Repetitions are not independent
query samples. Summaries reduce repetitions per query and retain round identity;
no confidence intervals, significance claims or final graphs are presented.
The 1M supplied-neighbor cross-check remains deferred. Run immutability is
enforced by the harness plus checksums/Git, not write-once hardware. `run.log`
contains harness messages and caught failure tracebacks; the daemon's local
PostgreSQL log is separate runtime state.

Operational qualification at 100k is established. Scientific approval to
spend compute at 250k+ is **not** established: stop for literature/novelty and
protocol review, including how a future multi-scale campaign should relate to
these standalone rounds, timing/cache variability and a revised resource budget.
No 250k, 500k or 1M experiment has been launched. No final research conclusion
is claimed.
