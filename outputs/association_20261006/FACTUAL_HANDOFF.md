# Metadata-association / physical-scale checkpoint — 6 October 2026

## Disposition: substantial progress, incomplete matched campaign

Two new physical stages completed: 100,000 rows/build1 and 250,000 rows/build1.
Both have independently verified retrieval/source/ground-truth/plan evidence.
**Both timing datasets are disqualified from AC-powered performance comparison.**
Host logs contradict the boundary AC strings, and record two actual sleeps
during the 250k radial arm. Neither raw bundle was edited to hide this.

The planned four-stage campaign is **not complete**. No second 250k build,
second 100k build, 500k stage or 1M stage was launched. Further database
benchmarking is paused for working-power confirmation and a corrected
sleep/power eligibility gate. Software tests passing is not host qualification.
The current A5 PDF is untouched; nothing was pushed remotely.

## Starting state, inspection and preservation

Started at `d3bcae685e2f61679e7dc1b7b230264480dffce1` on main, with one
pre-existing modification:
`raw_results/milestone_2/20260915T184137Z_bf300f7b1133/failure.json`.
It is a formatting-only edit and was neither staged nor restored.
Its working SHA256 remains
`3707e3624b10d59936c6d53de6d743e71b7346ba83f1359fdf207023d86f3e9b`.

Work was isolated in `filtered-vector-search-association`, branch
`research/metadata-association`, with ignored links to the existing local
runtime and virtual environment. Original project location:
`/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search`.
No directory/provenance paths were renamed.

The inspection covered Git state/history, existing factual handoffs, profiles,
source generation/loading, SQL/session settings, exact truth, timing boundaries,
plans, immutable artifacts, verification and analysis. Historical baseline:
213 tests passed. The negative/mixed preparation-policy result was retained;
there was no new warm-up tuning investigation. `STARTING_STATE.json` captures
858 historical evidence hashes; `HISTORICAL_INTEGRITY_CHECK.json` confirms all
858 remain unchanged in the original worktree.

## Decision and scientific question

Candidates, in descending value for the next core experiment:

1. Controlled metadata-association contrast plus a matched next physical scale.
2. Scale progression alone, leaving metadata geometry uncharacterized.
3. Offline query-level explanation without a controlled metadata intervention.
4. Another preparation-policy intervention without a new validity reason.

The first addresses an omitted variable and instructor feedback, uses the
same vectors/queries/graph for each paired metadata comparison, and reuses the
existing correctness machinery. Another warm-up study was not justified by
the prior evidence. Later host suspension was a new, concrete validity failure,
not a reason to chase perfect timing indefinitely.

Question: at fixed global filter selectivity, does deterministic geometric
concentration change recall/completeness/operational latency, and do paired
contrasts persist from physical100k to250k with inherited labels?
Proposed mechanism: query-local qualifying-neighbor density. No universal
direction of average quality or latency was predeclared. Strong geometric
association with little or inconsistent retrieval change would complicate the
hypothesis. The complete frozen design is in
`docs/METADATA_ASSOCIATION_PROTOCOL.md`; it remains an historical pre-run design,
not a claim that all planned stages succeeded.

## Dataset, metadata and controls

- Pinned SIFT1M HDF5 SHA256:
  `dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984`.
- 128-dimensional, unnormalized float32 vectors; Euclidean/L2 distance; k10.
- Base IDs ordered by SHA256 under `sift-base-v1|`; nested100k/250k prefixes.
- 200 measured query IDs and20 disjoint warmups, SHA256-ordered under
  `sift-query-v1|`; selection SHA256
  `70be57077cabbbca9c507e6e93f89ae7a55783f42d3ef984b7ea840e2ce198de`.
  Full IDs and vector hashes are in each run's `queries.json`.
- Legacy metadata: `filter_bucket = scale_rank % 100`, content-blind, not
  established statistically independent of vector geometry.
- New metadata: fixed base/train vector0 anchor; direct float64 squared L2;
  within consecutive100-row hash-order blocks, rank by `(score,base_id)` and
  assign `radial_bucket=0..99`. This is block-balanced radial-rank synthetic
  metadata, not semantic categories, clustering, or global radial quantiles.
- Both modes select exactly50/20/10/5/1%. At100k:50,000/20,000/10,000/5,000/1,000;
  at250k:125,000/50,000/25,000/12,500/2,500. Existing labels remain unchanged
  across scales, independently reconstructed and prefix-hash checked.
- Exact unfiltered source neighborhoods at40/100/1000 for all220 queries;
  L100 primary. D_s is the measured-query mean of `(local_fraction-s)^2`.
  Ninety-nine within-block PCG64 permutations, seed20261006. Predeclared gate:
  radial D exceeds both legacy D and permutation p95 at50% and5%.
  It passed at both scales. This is an engineering manipulation check, not a
  population significance test. No anchor selection or gate retuning occurred.

PostgreSQL17.11 (Postgres.app), pgvector0.8.6; Python3.12.0;
NumPy2.2.6, h5py3.14.0, psycopg3.2.9, pgvector-Python0.4.1, psutil7.0.0.
Python reports macOS15.0/x86_64; the prior preparation-policy handoff records
an inspected aarch64 PostgreSQL build. These are runtime/build observations,
not a new physical CPU identification. Four reported physical CPUs,16GiB RAM.
Logical CPU count was unavailable in the recorded host observations.

## Schema, SQL and execution evidence

Two tables in the new `association` schema, leaving historical schemas intact:

```sql
id integer PRIMARY KEY CHECK (id >= 0),
scale_rank integer NOT NULL CHECK (scale_rank >= 0),
filter_bucket smallint NOT NULL CHECK (filter_bucket BETWEEN 0 AND 99),
radial_bucket smallint NOT NULL CHECK (radial_bucket BETWEEN 0 AND 99),
embedding vector(128) NOT NULL
```

`association.sift_exact` has one B-tree per metadata column, no vector index.
`association.sift_hnsw` has one HNSW index, no metadata B-tree. Both tables
receive both metadata columns before graph construction. Modes share the same
tables/graph without UPDATEs; all seven physical relation identities are
checked before/after both modes. Each scale loads fresh tables and builds a
fresh graph; OIDs and filenodes differ between stages.

Representative exact workload SQL, radial5%:

```sql
SELECT id, embedding <-> %s::vector AS distance
FROM association.sift_exact
WHERE radial_bucket < 5
ORDER BY distance, id LIMIT 10
```

Standard and iterative HNSW share this one-bound-vector SQL:

```sql
SELECT id, embedding <-> %s::vector AS distance
FROM association.sift_hnsw
WHERE radial_bucket < 5
ORDER BY distance LIMIT 10
```

Legacy replaces the predicate column with `filter_bucket`; all five literal
thresholds are frozen. Ground truth uses the exact table, `ORDER BY distance
FETCH FIRST 10 ROWS WITH TIES`, then canonical distance/ID ordering and a
recorded strict/boundary tie partition.

HNSW: vector_l2_ops, m16, ef_construction64, ef_search40;
iterative_scan off versus strict_order; max_scan_tuples20000;
scan_mem_multiplier1. Build maintenance_work_mem1GB, parallel maintenance0.
Exact planner scan paths remain enabled; ANN disables sequential/bitmap paths
and must execute exactly Limit→HNSW Index Scan. JIT off, generic prepared plans,
statement_timeout2min, exact work_mem4MB, ANN64MB, shared_buffers128MB.
Planner cost/parallel controls are preserved from the preparation protocol.

At250k the representative legacy50% exact plan actually used
`Limit → Gather Merge → Sort → Seq Scan`; legacy20/10/5/1% used
`Limit → Sort → Bitmap Heap Scan → Bitmap Index Scan`.
The exact baseline is therefore a real planner-chosen filtered exact path,
not an artificially forced sequential scan. Every ANN audit used its intended
HNSW scan with the correct metadata post-filter and single generic `$1` order.
All30 audits per stage execute the actual workload's prepared statement.
Each statement finished with1022 generic and0 custom executions.
Plan timings are not presented as qualified performance evidence.

## Measurement and verification scope

Each stage:2modes×3methods×5filters×200queries×5repetitions =30,000 measured
calls;600 disjoint warmups. Persistent method sessions; normal client
`perf_counter_ns` execute+fetch timer, separate plan/scoring/persistence work.
CHECKPOINT and verified shared-buffer eviction before each mode; no OS-cache
flush or server restart claim. No measured-query exposure preparation pass.
All five repetitions, including first passes and shortfalls, are retained.

Canonical Recall@10 = unique returned-ID/exact-canonical-ID intersection /10.
Tie-aware recall credits all strictly closer matches plus eligible boundary
ties, capped by remaining top10 slots, /10. Completeness is returned_count=10;
shortfall is10-returned_count. All filters have at least10 true qualifying rows.
Exact must have recall1 and return10. Completeness and recall are different:
returning ten approximate neighbors is not proof they are the correct ten.

Query ID is the primary comparison unit; repetitions are technical repeats;
physical graphs are higher-level blocks. Planned latency p50/p95 were across
200 five-pass query medians, with raw-request p95 and per-pass diagnostics
separate. Those latency comparisons are now excluded for these runs.
Quality means average each query's five observations, then the200 queries;
metadata contrasts pair the same query/graph. One graph per scale is available,
not two-build replication. Do not treat60,000 calls as independent samples.

Both independent stage verifiers passed:30,000 measured+600 preparation
observations each;2,000 truth records plus full deterministic reexecution;
40 fresh NumPy truth checks;220 recomputed exact source neighborhoods;30 plans;
metadata, prefix inheritance, source-stream checksums, source commit, physical
identity, SQL/settings, schedule, recall/completeness, result distances,
checkpoint coverage and before/after raw hashes. The offline verifier reuses
explicitly disclosed checksum/recall/chunk/plan/source/NumPy helpers; it is not
an independent database engine. Its power checks are insufficient, as observed.

## Chronology, run IDs and commits

1. `8d83d285d16f1decb41ffd4b43f4a8d0d0352983`: frozen design, mode-aware
   adapter/runner, metadata construction, verifier, analysis and98 new tests.
2. `20261006T175652Z_5367e3fe7857`: physical100k/build1, source8d83d28,
   independently verified and committed as
   `9047f081058541920ebf77ca39554bce2a7e98fb`.
3. `20261006T180734Z_dcf7ada71ed5`: physical250k/build1, source9047f08,
   unchanged experiment bytes, independently verified. Preserved with the
   host-timing disqualification as
   `2da59d007adb0edd035e2189d9c1be747c1a25b7`.
4. A fail-closed timing-analysis guard, explicit quality-only reduction,
   independent arithmetic proof and this handoff follow in later commits;
   their exact hashes are listed in the final chat/Git history. No backdating,
   history rewriting, silent retries or remote push.

Both raw roots are under `raw_results/association/`. Each contains252 payload
files plus COMPLETE/checksum markers. All later qualifications are external
annotations; a COMPLETE marker authenticates the implemented producer gates,
not every possible scientific-validity condition.

## Host failure and corrections

The 100k run began12:56:52CDT and completed13:05:18; log summaries report
battery operation at12:58 and13:02–13:03 despite boundary AC strings.
The 250k run began13:07:34 and completed13:31:02. Its radial iterative50% block
overlapped a sleep13:22:48–13:23:31; its radial exact20% block overlapped a
sleep13:25:13–13:26:28. The scoped log reports battery use during both sleeps.
Battery snapshots also show discharge. The physical cause of conflicting AC
telemetry is not established; do not invent one.

The boundary checker only checks an AC substring and identical power settings;
it neither detects transient power changes nor qualifies continuous wakefulness.
This was discovered from elapsed-time discrepancies and confirmed with the
system sleep/wake log. The whole timing dataset of each stage is quarantined,
not only selected slow rows. `HOST_VALIDITY_REVIEW.json` and
`POWER_EVENT_EXCERPT.txt` supersede any earlier statement that the first stage
was a qualified timing reference. The normal analysis command now rejects
these known runs before producing latency analysis.

Other corrections before data collection: producer/verifier algorithm and
gate-field alignment; six concurrency-boundary checks; inherited prefix hashes;
all-three-method prepared-session assertion; association-specific prepared SQL
collector; stricter source/schema/truth provenance. A test initially confused
macOS `/var` with resolved `/private/var`; its path assertion was corrected.
During handoff, saving a proof with the raw-run-only writer was correctly
refused; the verifier was rerun and its proof saved outside the immutable run.
`shasum` needed `LC_ALL=C` on this host. Process inspection was sandbox-denied;
no permissions were bypassed. These are distinct from empirical retrieval errors.

## Remaining limits and next action

Resolve working external power first; reject contradictory telemetry. Add a
bounded sleep-inhibition mechanism plus recorded whole-interval sleep/power
qualification, freeze that correction, and rerun the matched four-stage chain
from a fresh100k reference. Do not splice clean future timings into this chain.
The current runner's boundary-only host gate is not sufficient for new timing.
No 500k/1M progression is scientifically qualified yet.

Retain the metadata construction and correctness infrastructure: the evidence
supports a real local-association contrast and physical250k loading. It does
not support qualified latency/throughput claims, universal cache explanations,
graph-traversal causality, final scale trends, production routing rules or ANN
novelty. Further generalization is limited by one anchor/metadata realization,
one dataset/host,200 fixed queries, one graph per scale, nested dependent
filters/scales, fixed search effort and unequal exact/ANN work_mem.
Exact top40 density is a descriptive proxy, not pgvector's actual candidate set.

Focused primary literature informed the design: pgvector0.8.6 documentation
and ACORN already cover predicate-dependent ANN behavior; no novelty claim is
made. Search effort may warrant a later controlled follow-up, but this run does
not automatically add that axis or authorize larger scales.

## New empirical quality evidence — descriptive, not final findings

`quality_checkpoint/QUALITY_CHECKPOINT.md` contains every one of the60
mode/method/filter/scale condition rows and30 paired metadata contrasts;
the adjacent JSON preserves per-query quality and local-density descriptors.
It deliberately publishes no query-latency measurements. Two figures were
generated from verified data and visually checked for readable labels/legends.

| Observed condition | 100k legacy → radial | 250k legacy → radial |
|---|---:|---:|
| Standard HNSW,50%, mean canonical Recall@10 | 0.9645 → 0.5690 | 0.9435 → 0.5620 |
| Standard HNSW,50%, returned ten | 99.5% → 54.5% | 100% → 55% |
| Iterative HNSW,1%, mean canonical Recall@10 | 0.9835 → 0.5245 | 0.9730 → 0.5005 |
| Iterative HNSW,1%, returned ten | 100% → 55% | 100% → 53.5% |
| Standard HNSW,5%, mean canonical Recall@10 | 0.2145 → 0.2055 | 0.2050 → 0.1835 |
| Standard HNSW,5%, returned ten | 0% → 12% | 0% → 12% |

Exact matches canonical ground truth and returns ten throughout. All12,000
query-condition cells have identical ordered result IDs/distances and quality
across five repetitions. Canonical and tie-aware recall are both retained.
These examples demonstrate why recall and completeness must not be conflated:
radial metadata can increase complete-answer frequency while mean recall falls.
Do not summarize the effect as universally harmful or beneficial.

The local-association check is quantitatively strong: at5%, D changes from
0.000531 to0.0278255 at100k and0.000510 to0.027085 at250k; permutation p95
references are0.0005428 and0.000562. At50%, radial D is0.226298 and0.2265335,
versus legacy0.002277 and0.0024415. These are observed source-neighborhood
properties for the fixed queries, not estimated population effects.

At5% radial metadata,130/200 measured queries at100k and137/200 at250k have
zero qualifying members among exact unfiltered top40 neighbors. In the100k
standard-HNSW results, that zero-density group returns zero results; the23
queries with at least10 qualifying top40 neighbors return ten, averaging
Recall@10≈0.9391. At250k the corresponding23-query dense group also returns
ten, averaging≈0.9348; the zero-density group averages0.0146 returned rows.
This is a query-level descriptive link, not proof of pgvector's traversal path.
The tested analyzer reports top40-density/recall Spearman≈0.9922 and0.9855 for
those two standard/radial5% conditions. No p-values or causal claims are made.

Independent stdlib-only arithmetic in `verify_quality_checkpoint.py` recomputed
all60,000 measured results from returned IDs and exact truth and checked4,000
truth-record checksums/partitions. **72,960 published quality values matched,
zero discrepancies**, including condition means, per-query quality, paired
differences and repetition-stability counts. Raw/source hashes remained
unchanged. Density/rank-correlation arithmetic and figure rendering are outside
that particular checker; source neighborhoods/metadata are independently
reconstructed by stage verification, rank/group logic has focused tests, and
the two figures were visually inspected. These validation scopes are distinct.

Supported inference: global selectivity alone does not describe the quality
behavior of these fixed-settings queries under the two tested assignments.
Hypothesis for a future controlled test: local qualifying-neighbor density and
the bounded iterative search budget help explain the observed shortfalls.
Alternative explanations/limits include cohort difficulty, approximate-neighbor
misses, graph realization and fixed-anchor specificity. Replication and an
effort intervention would help distinguish/generalize those explanations.

## Resources and cost observations

These are recorded operational/preparation costs, **not qualified comparative
performance results or reliable larger-scale runtime projections**.

| Recorded quantity | 100k/build1 | 250k/build1 |
|---|---:|---:|
| Exact schema+COPY seconds | 8.2302 | 13.6956 |
| HNSW build seconds | 86.4822 | 216.6268 |
| Initial truth generation, both modes, seconds | 27.4548 | 71.3600 |
| Exact table total bytes, including its indexes | 62,922,752 | 158,244,864 |
| ANN table total bytes, including its indexes | 144,359,424 | 361,578,496 |
| HNSW index bytes (already in ANN total) | 83,132,416 | 207,364,096 |
| Minimum sampled available host RAM bytes | 4,352,602,112 | 3,574,681,600 |
| Minimum sampled disk-free bytes | 32,915,931,136 | 32,088,428,544 |
| Maximum reported runner RSS bytes | 443,162,624 | 1,026,473,984 |

RAM/disk values are180 pass-boundary snapshots per stage, not continuous
minima. Runner RSS is not PostgreSQL or whole-host peak memory. Initial truth
cost excludes the separately recorded full reexecution and NumPy checks.
The live association tables remain at250k; the earlier physical graph was
replaced by the next load, while its complete raw evidence remains preserved.
No server restart or stop was performed for these stages.
Storage headroom was adequate; host power/sleep validity, not a proven storage
or query correctness failure, stopped expansion. A fresh campaign needs four
loads/graphs and verification; no500k/1M runtime estimate is justified here.

## Exact principal commands and final checks

Commands ran from the `filtered-vector-search-association` worktree with the
existing `.venv-milestone2`. Investigation/read-only Git/file commands were
also used; the empirical and verification entry points are:

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m unittest discover -s tests -p 'test_*.py' -q
.venv-milestone2/bin/python -m pip check
for script in scripts/postgres_local.sh scripts/bootstrap_postgres_macos.sh scripts/load_smoke_data.sh scripts/clean_results.sh; do bash -n "$script" || exit; done
git diff --check
git diff --cached --check

PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.association.runner --scale 100000 --build 1
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.association.verify raw_results/association/20261006T175652Z_5367e3fe7857
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.association.runner --scale 250000 --build 1 --previous raw_results/association/20261006T175652Z_5367e3fe7857
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.association.verify raw_results/association/20261006T180734Z_dcf7ada71ed5

PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python outputs/association_20261006/build_quality_checkpoint.py --host-evidence outputs/association_20261006/HOST_VALIDITY_REVIEW.json
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python outputs/association_20261006/verify_quality_checkpoint.py --output outputs/association_20261006/INDEPENDENT_QUALITY_VERIFICATION.json
```

The generator/proof refuse existing output destinations; reproducing them
requires a fresh `--output` path. This is intentional, not a request to delete
evidence. The benchmark commands above document what ran, **not authorization
to rerun the known-inadequate power gate**. The normal timing analyzer now
fails closed for these two known disqualified run IDs.

Complete suite:311 passed in63.981s before experiments;311 passed in72.094s
after the analysis quarantine guard. The 98 additions comprise 14 metadata,
13 database, 6 protocol, 29 runner, 20 verifier and 16 analysis tests.
All 63 Python files later passed AST parsing. Dependency,
shell-syntax and diff checks passed. The final shell check above invokes
`bash -n` separately for each of the four scripts; an earlier multi-argument
invocation only parsed its first script and was insufficient for that claim.
Nonfatal plotting-cache/deprecation
warnings are recorded; mock INVALID lines are deliberate tests, not hidden
empirical retries. See `FINAL_TEST_RESULT.txt`, both STAGE verification JSONs,
the independent arithmetic proof, and the historical integrity record.

Both database runs started from clean commits. Later analysis generation
recorded the in-progress analysis/docs/output-script changes and their hashes;
no benchmark source bytes or raw files changed. Current exact HEAD and final
Git status are provided in the final chat and can be obtained with
`git log -1 --format='%H %s'` and `git status --short`.

## Important files and exact inventory

`FILE_INVENTORY.txt` enumerates every added/changed repository file relative to
the starting commit. Important entry points:

- `config/metadata-association-v1.json`: frozen planned four-stage profile.
- `docs/METADATA_ASSOCIATION_PROTOCOL.md`: hypotheses, controls, gates and limits.
- `experiments/association/metadata.py`: deterministic labels, exact source
  neighborhoods and prespecified permutation-reference manipulation check.
- `experiments/association/database.py`: new schema/load/index, two-mode SQL,
  physical/source validation, truth and actual prepared-plan audits.
- `experiments/association/protocol.py`: frozen profile and matched schedules.
- `experiments/association/runner.py`: one physical stage, gates, durable
  observations and immutable completion/failure artifacts.
- `experiments/association/verify.py`: offline source/metadata/neighborhood,
  truth/result/plan/grid/provenance/immutability verification.
- `tests/association/`:98 new focused tests; existing suites remain unchanged.
- `analysis/metadata_association.py`: descriptive paired analysis; default
  reporting now rejects known host-disqualified inputs.
- `raw_results/association/20261006T175652Z_5367e3fe7857/` and
  `raw_results/association/20261006T180734Z_dcf7ada71ed5/`: immutable evidence.
- `outputs/association_20261006/`: starting/final integrity, explicit host
  disqualification, stage proofs, quality-only generator/report/figures,
  independent arithmetic checker/proof, tests and this handoff.
- `README.md`: current status and explicit stop condition, without changing
  historical smoke commands or old evidence bundles.

## Required factual A5 changes and demonstration

Based on the preserved October6 A5 review; no new PDF edit has been made:

1. Add the newly executed physical250k stage and controlled metadata contrast
   to the cumulative dated history. Do **not** claim two new builds per scale
   or a completed four-stage campaign: only100k/build1 and250k/build1 ran.
2. Record60,000 new measured calls,1,200 warmups,60 plan audits,4,000 truth
   records with full reexecution,80 fresh NumPy checks and311 current tests.
   Keep September/earlierOctober checkpoint counts dated, not overwritten.
3. Explain content-blind legacy metadata versus block-balanced radial ranks,
   equal global proportions, inherited labels and measured local association.
4. Show quality-only results with one-graph-per-scale caveats. Explicitly state
   that timing is disqualified by battery/sleep evidence; omit these latency
   comparisons from any performance conclusions. Keep the earlier mixed
   preparation-policy result separate, without claiming a cache cause.
5. Add the boundary-power-gate blind spot, immutable evidence preservation and
   timing quarantine as the major new challenge. Its detection/disposition is
   resolved; physical power and the corrected continuous eligibility gate are
   still unfinished. Historical timing is not proven invalid by this discovery,
   but its boundary-only power checks also should not be overstated.
6. Update remaining work: repair host qualification, fresh matched replication,
   then decide larger-scale/effort follow-up.500k/1M and final generalized
   conclusions remain incomplete. Use actual dates and the instructor's accepted
   Week7 cutoff, not invented weekly accomplishments or on-schedule claims.

Best3–5 minute video sequence, using files under the original project root:

- 0:00–0:35: research question and the top of `README.md`, including incomplete
  status/timing warning.
- 0:35–1:15: `experiments/association/database.py`, showing the single vector
  binding, planner-enabled exact baseline and same-graph predicate contrast.
- 1:15–1:50:250k `database_evidence.json`, then
  `plans/legacy_033f48b3ad84515609da.json` for actual exact50% execution and
  `plans/radial_92fe34b3ecb0da4dd5e5.json` for actual iterative1% execution.
  Both plan paths are under the250k raw root above.
- 1:50–2:45: `outputs/association_20261006/quality_checkpoint/local_density.png`
  and `retrieval_quality.png`; state one graph per scale and no eligible timing.
- 2:45–3:30: `INDEPENDENT_QUALITY_VERIFICATION.json`, `FINAL_TEST_RESULT.txt`
  and `HOST_VALIDITY_REVIEW.json`: actual evidence, not a slide-only demo.
- 3:30–4:15: next steps and student-owned explanation of the limitations.

These are exact files to show; no screenshots of a completed four-stage campaign
were created or implied. The figure files themselves are the best visual
artifacts. The current PDF remains at its existing Downloads path, unchanged.

## Questions the student should be able to defend

1. Why do within100-row ranks preserve exact counts and inherited labels, and
   why is that not statistical independence or global radial quantiling?
2. What does D measure, why include mean displacement, and what does the
   permutation manipulation check fail to establish?
3. Why can standard or bounded iterative HNSW return fewer than ten despite
   thousands of globally qualifying rows? Why is completeness not recall?
4. What stays physically identical across metadata modes, and what remains
   confounded when the scale/graph changes?
5. Why are60,000 calls not60,000 independent samples, and how do query-median
   p95, raw-request p95 and repetition diagnostics differ?
6. Why do311 passing tests and a COMPLETE marker not make host timing valid?
   How do the preserved power log and external quarantine change the claim?
7. Which results were independently recomputed, which helpers were reused,
   and which parts can you personally explain/reproduce with tool assistance?

The strongest immediate next task is a narrowly corrected host-qualified
replication of this same core experiment, not another broad warm-up study and
not an automatic500k run. Retained quality evidence makes that replication
scientifically worthwhile; it does not remove the need for it.
