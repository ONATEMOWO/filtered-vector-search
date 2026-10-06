# Adversarial research audit — checkpoint 38baba3

Audit date: 6 October 2026. This is a technical review, **not assignment prose,
a finished A5 submission, or a novelty claim**. Audit preceded all new edits.
No database experiment, restart, data load or index build was performed for this review.

## 1. Decision and scope

**Operationally strong; scientifically narrower than the original question.**
The evidence supports reproducible, descriptive comparison of three configured
PostgreSQL/pgvector paths at one full benchmark scale. It does not yet identify
a dataset-scale effect, a metadata-correlation effect, a universal routing rule,
or steady-state latency.

Highest-priority findings:

| Priority | Finding | Consequence |
|---|---|---|
| High | Strong first-versus-later repetition differences in existing HNSW timings | Do not equate 20 warm-ups with demonstrated steady state; retain all repetitions and diagnose order sensitivity |
| High | No matched full multi-scale experiment, and no correlation treatment | Scale and correlation hypotheses remain untested |
| High for provenance; limited scope | One historical failed-run JSON was reformatted before this audit | Its byte checksum fails; leave it untouched and disclose the deviation; successful full-run evidence still verifies |
| Medium | Completed observations remain only in memory until all blocks finish | Future interruption can lose partial evidence; fix before longer runs, not by editing completed results |
| Medium | Exact work_mem and server/planner controls are recorded but incompletely frozen in configuration | Current result is a configured-system comparison, not equal-resource algorithm isolation |
| Medium | Only 200 query vectors and two graph constructions | No 30,000-independent-sample inference or precise graph-population uncertainty |
| Low/medium | Stale README scope, one measured query used in premeasurement audits, partially shared verifier helpers | Tighten terminology and future protocol; no demonstrated wrong existing recall/plan |

The bounded addition selected after audit is an **offline repetition-sensitivity
diagnostic of the already verified full-100k runs**, with focused tests.
It is not another benchmark and does not change which timings count.
It completed with 20 focused tests and 148 tests passing in the full suite.
Details and exact results are in [verification record](VERIFICATION.md).
No correlation generator, routing policy, future executable config or larger
run is implemented in this review.

## 2. Research reconstruction and progression

Original question, unchanged in wording since Milestone 1:

> How do filter selectivity and dataset scale affect the recall and query
> latency of standard HNSW and iterative HNSW filtered vector search compared
> with exact filtered search in PostgreSQL/pgvector?

Actual question measured so far:

> For one fixed 100k SIFT subset on PostgreSQL 17.11/pgvector 0.8.6 on this
> laptop, at L2/k=10 with rank-modulo-100 metadata and fixed HNSW settings,
> how do the five nested selectivities relate to recall, completeness and
> prepared execute-and-fetch latency for three deliberately selected paths,
> across 200 fixed queries, five repeats and two physical graph builds?

This is operational narrowing plus methodological refinement, not a new formal
research question. The one-million-row source file is not a completed one-million-row
experiment. Full 100k is a standalone campaign, not a partial ascending/descending
multi-scale run that can silently be continued.

| Research pressure → decision | Implementation / commit | Evidence / discovery → correction → next pressure |
|---|---|---|
| Prove real plumbing → small synthetic smoke | `cd199a2`: 20k vectors, 128D, seed 20260915, exact + standard | Real plans exposed metadata-index misrouting; forced/verified paths and 250 measurements established pipeline, not a research finding → use real geometry |
| Fairer real-data comparison → SIFT and separate exact table | `61519cd`: pinned HDF5, metadata B-tree exact baseline, iterative HNSW, same-query client timing | Replaces forced-sequential exact and separate EXPLAIN timing of M1 → actual version/truth checks |
| Vendor-labelled version string rejected → retain failure and correct numeric gate | `8682a76`; first INVALID Sep15 run | PostgreSQL 17.11 (Postgres.app) was correct; reject true version drift, not vendor suffix → truth/aggregation refinement |
| Deterministic truth and query-level statistics | `8f537a4`, `0f5fe34` historical corrected 10k | Subsequent stricter audit superseded this evidence → preserve, do not pool |
| Verify timed SQL itself → single bound vector and prepared generic EXPLAIN | `97eb5b0`; also missing preflight projection flag and finalization guards | Prevents assumptions about an independently planned SQL copy → independent artifact check |
| Independent p95 arithmetic differed 1 ns → bounded tolerance only for p95 | `6708bfa`, then `8f62bb3` corrected 10k | 75 measured calls, 1,000 truth records/rechecks, 20 NumPy checks, 15 plans → physical 100k qualification |
| Permission failure before load → retain INVALID attempt | `5549ad1`; retry `1b68328` | Actual new 100k graph, 600 calls and resources verified → larger sample at the same scale |
| User-authorized full 100k only → explicit addendum | `5d6a16f`; `3692827` descriptive qualification figures | Real restart required, no eviction substitution for full rounds → two full physical rounds |
| Replicate build → round 1 and round 2 | `e7952e5`, `f671005` | 15,000 calls each; different physical objects, same source/data/truth; pair verifier passes → inference limits and novelty review |
| Package evidence → stop before 250k | `fa5a03f`, `38baba3` | Evidence index and checksums → current audit reveals repetition effects and one later formatting mutation |

Git supplies dates September 15 and 29, not a seven-week diary or evidence of
individual conceptual ownership. Use dated milestones; do not invent work in
weeks without records. The supplied A5 instructions explicitly allow milestone
organization.

## 3. Claim / evidence / uncertainty ledger

Types: **O** observed; **G** implementation guarantee (within stated scope);
**I** inference; **A** assumption; **H** hypothesis; **U** unsupported generalization.
A successful check can support O/G without establishing scientific validity.

| Claim and type | Evidence | What would contradict it / required check | Uncertainty or threat |
|---|---|---|---|
| O: both full 100k rounds completed the declared 15,000-call matrix | E11, raw execution grids; pair verifier rerun Oct6 passed | Missing/duplicate grid key, error row, source/hash mismatch | Proves recorded workload coverage, not generalization |
| O: source/table/query linkage and intended plans passed recorded checks | E4/E8/E10/E11 | Wrong vector bytes, filter count, prepared SQL, index route or row identity | No live DB revalidation was performed Oct6; historical actual execution evidence plus fresh offline verification |
| O: exact recall/completeness is one on measured calls | E12, scored IDs, exact truth | Recomputed mismatch or independent brute force disagreement | Most truth records are PostgreSQL exact plus deterministic re-execution, not 1,000 independent NumPy searches |
| O: at 1%, standard full-run mean canonical recall is 0.042; iterative 0.9835 | E12, both builds | Recomputed intersection/tie/scoring mismatch | Descriptive fixed-scope fact, not universal treatment effect |
| O: iterative returned ten in all full-run conditions, but not always exact top ten | E12 | Incomplete raw row or recall one everywhere | Completeness is not recall; strict ordering is not exact retrieval |
| O: first-pass HNSW latency can be much larger than later passes | Existing full executions; new offline diagnostic | Paired recomputation fails or condition/repetition labels are wrong | Cause not identified; later-pass values must not replace primary results retrospectively |
| A/I: content-blind hashing is a useful geometry-neutral control | E5, formula reads IDs/rank only | Neighborhood-label diagnostic detects association beyond a declared null | Realized empirical independence is unmeasured; exact counts constrain labels; physical placement is periodic |
| G: predicates are nested and marginal match counts exact at planned multiples of 100 | E5, filter_counts.json | Count/nesting mismatch or changed metadata semantics | Does not imply independent conditions or realistic label skew |
| G: runner refuses writes to finalized run directories through its artifact API | artifacts.py, terminal-state tests | Bypass/edit outside API; missing checksum/marker protection | Not filesystem immutability: present dirty historical JSON demonstrates boundary |
| O: current successful runs have verified byte manifests | Oct6 audit: seven pass, one old INVALID run fails | Any additional mismatching payload | Cannot currently say “all eight pass” or “worktree clean” |
| O: real server restarts were verified | E9/E11, cache_reset.json | Same postmaster start, changed cluster/objects across boundary | OS cache survives; plan audits and workload subsequently repopulate buffers |
| U: warm-up eliminates cache/history effects | No sufficient evidence; repetition diagnostic contradicts equivalence | Controlled stationarity/pilot evidence under a declared criterion | No continuous cache/thermal/concurrent-workload tracing |
| H: changing scale changes a quality-qualified crossover | Future design only | Matched scale experiment shows stable ranking within uncertainty | 10k/100k stage contrasts are confounded |
| H: changing query–predicate correlation matters at fixed selectivity | Future design only | Achieved correlation contrast without material outcome change | No correlated metadata or query-alignment treatment currently exists |
| U: 30,000 timings are 30,000 independent observations | Refuted by design E7/E11 | N/A: repeated query IDs explicitly recorded | 200 unique queries, reused across conditions/builds; two graph realizations |
| U: this establishes novelty, planner defects, or a best routing policy | No such experiment or systematic literature comparison | Held-out policy evaluation and prior-art review required | Forced ANN routes and separate tables deliberately avoid a unified planner decision |
| U: existing code/tests prove individual mastery or completed A5 | Not inferable | Student explanation/demo and actual report/video submissions | Draft/proposal not supplied; assisted work must be represented honestly |

## 4. Experimental-control matrix

Evidence keys resolve to exact files below. S = strong control; W = weakness;
A = ambiguity; M = missing. Severity refers to an overclaim or future study,
not automatic invalidation of the existing descriptive records.

### Data and metadata

| Dimension | Observed control / status | Severity and remaining issue | Exact evidence |
|---|---|---|---|
| Identity/version | S: canonical ANN-Benchmarks HDF5, 525128288 bytes, SHA256 dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984 | Low; external download availability still needed for clean reproduction | E2 dataset; E15 |
| Shape/metric/type | S: 1M base, 10k source queries, 128D float32; L2, no normalization; stored vector(128) | Low within scope; no cosine, learned embedding or precision comparison | E2; E5 validate_hdf5 |
| Physical scale | S: separate actual tables and graph for 10k or 100k; no predicate simulation over a bigger graph | High if described as a scale result; 250k/500k/1M never measured | E4:98–183; E11 |
| Subset construction | S: prefixes of global SHA256(sift-base-v1\|id) order, fixed checksum | M: one subset realization; not multiple samples of a population | E5:40–140,375–408 |
| Query construction | S: first 200 hash-ranked test IDs, next 20 warm-ups; qualification prefixes 5/20 | M: difficulty-stratification/generalization not assessed | E5 select_query_ids; queries.json |
| Query reuse | S: same 200 IDs across all methods/filters/full rounds | W: pairing must be retained; reused IDs are not independent observations | E11 query_manifest_sha256; E7 |
| Ordering | S: insert globally ranked vectors in identical order in both tables | M: only one insertion order; graph construction/order sensitivity untested | E4:111–134 |
| Metadata semantics | S: bucket = global rank mod 100, not a vector-derived category | High construct threat if called realistic/semantic or iid random | E5:375–408; schema comments |
| filter_threshold | S: literal t means bucket < t; at 100k, t=1 selects exactly 1,000 rows | Low implementation risk; “selectivity” means match fraction (smaller is more restrictive) | E4:455–468; filter_counts.json |
| Distributions | S: 50k/20k/10k/5k/1k at 100k; 5k/2k/1k/500/100 at 10k | M: no natural skew, multi-attribute predicates, tenants or empty result sets | E14; filter_counts.json |
| Nesting/overlap | S: 1% subset of 5% subset of 10% subset of 20% subset of 50% | Medium: responses and truth sets related; not five independent populations | E5; predicate definitions |
| Seed behavior | S: domain strings and hashes, not a numerical RNG seed, determine M2 labels/subsets/queries | M: no metadata-seed replication; M1 seed20260915 is not an M2 random seed | E2; E5 |
| Geometry independence | S: generator never reads vector geometry to assign labels | A: no empirical local-association/null check; content-blind is not a realism proof | E5:375–408 |
| Physical label locality | W: every100 insertion ranks repeats the same bucket sequence | Medium: exact bitmap/heap access is a synthetic layout property | E4:111–134; E5 |
| Correlation/skew | M: no cluster/neighborhood/anti/graded treatments | High for H5 or “feedback fully resolved” | E2 has only rank-modulo mode |

### Search and HNSW

| Dimension | Observed control / status | Severity and remaining issue | Exact evidence |
|---|---|---|---|
| Exact truth | S: exact-only table, WITH TIES, canonical distance/id top10 | Low within stored precision; no supplied filtered truth misuse | E6:17–73 |
| Realistic exact performance path | S: metadata B-tree, all exact scan paths enabled, no vector index | Medium: configured-system baseline, not exhaustive best exact implementation | E4:284–313,414–441 |
| Actual exact plans | S: 50% parallel sequential; selective filters bitmap heap/index in full rounds | M: not a study of planner's choice between exact and ANN on one table | full plans/plan_assertions; E11 |
| SQL shape | S: one bound vector, exact ORDER BY distance,id; ANN ORDER BY distance | Low: tie conventions differ intentionally; report both canonical and tie-aware recall | E4:455–475 |
| Prepared statements | S: actual generic EXECUTE audit and matching SQL/parameter/counters | Low hardening gap: verifier accepts final counter lower bound; actual runs show1022generic/0custom per statement | E8:181–218; E10:735–739; prepared_statements.json |
| Method routing | S: HNSW seq/bitmap disabled, required HNSW Index Scan and post-filter asserted | High if claimed to measure default optimizer/routing behavior | E8:80–147 |
| Output semantics | S: qualifying unique in-scale IDs, sorted finite nonnegative distances, returned count/shortfall retained | M: observed full completeness is not an algorithm guarantee | metrics.py; E12 |
| Build configuration | S: L2 class, m16, ef_construction64; maintenance_work_mem1GB; serial maintenance build | M: no parameter tuning or optimal frontier comparison | E2 hnsw; E4:141–173 |
| Standard search | S: ef_search40, iterative_scan off | A: ef_search is not all vectors examined; candidate-yield model is illustrative | E4:414–441; pinned external pgvector docs |
| Iterative search | S: strict_order, ef40, max_scan_tuples20000, scan_mem_multiplier1, work_mem64MB | Medium: finite/approximate cap; relative budget changes as N grows | E2; method_sessions.json |
| Graph randomness | S: fresh physical graph per full round; shared by both ANN methods | M: construction RNG seed/serialized topology not controlled; two builds do not characterize graph distribution | E11 distinct OIDs; no seed field in E2 |
| Build/size measurements | S: full builds88.180/87.150s; index83132416bytes in qualification | W: timing/resource observations specific to one laptop | E12 phase/resource table; relation_sizes.json |
| Exact vs ANN memory | A: actual exact work_mem4MB vs ANN64MB; exact can use parallel workers | Medium: explicit resource asymmetry, not demonstrated bias; freeze before cross-host reproduction | full method_sessions.json; E4:414–441 |

### Timing and system state

| Dimension | Observed control / status | Severity and remaining issue | Exact evidence |
|---|---|---|---|
| Clock/boundary | S: perf_counter_ns around prepared execute + fetchall of the scored rows | Low; includes adaptation/driver/transport/decode, excludes post-fetch Python coercion/scoring | E4:486–502 |
| Client vs server | S: M2 client-observed; M1 uses separate EXPLAIN Execution Time | High if pooled or described as the same latency metric | README:151–172; E4 |
| Connections/preparation | S: persistent method connections; prepare outside timed calls | A: method connections differ but transport is same; no throughput/concurrency experiment | E7:800–835; E4 |
| Concurrency | S: one harness query at a time | A: not proof that whole machine or PostgreSQL had no other work | E2 concurrent_queries; runner loop |
| Warm-ups | S: 20 disjoint warm-up vectors per block | W: insufficient evidence of stable timing; repeated measured pass effect observed | E7:842–970; diagnostic |
| Audit contamination | A: one measured vector executes twice per method/filter before warm-up | Low but real: disjoint warm-up set does not mean all measured vectors were unseen | E7:810; E8:194–209 |
| Shared buffers/reset | S: qualification verified eviction; full runs verified real postmaster restart | Medium if stages treated interchangeable; both then execute plans/warm-ups | cache_reset.json; E9 |
| OS cache | S: explicitly not flushed | High for cold-cache claims; its state is not held equal across all conditions | E2 cache_policy; E3 |
| Cache size | S: recorded shared_buffers128MB; exact+ANN relations exceed it | A: warm state depends on paths and preceding blocks; no automatic cache residency guarantee | postgres_settings.json; relation_sizes.json |
| Block order | S: deterministic hash-shuffle with round/stage/scale identities | W: 15 long method/filter blocks, not per-query method interleaving; carryover/time drift remain | E7:159–207 |
| Within-block order | S: five full hash-shuffled query passes, not consecutive repeats of one query | W: repetition number also elapsed time/history, confounding causal attribution | E7:892–970 |
| Host control | S: versions/AC/energy at boundaries, phase RAM/disk/client RSS snapshots | M: continuous background load, CPU frequency, thermal pressure and server peak RSS not established | E4:537–555; resource_observations.json |
| Statistics changes | S: VACUUM ANALYZE FREEZE, stats target1000, checkpoint; no intentional timed mutations | A: no global isolation; autovacuum on; SHOW ALL captured but all parameters not gated | E4:175–182; postgres_settings.json |

### Correctness, statistics and reproducibility

| Dimension | Observed control / status | Severity and remaining issue | Exact evidence |
|---|---|---|---|
| Truth re-execution | S: all1,000 combinations rerun identically per run | A: same engine/algorithm agreement is not independent correctness proof | ground_truth_reexecution.json; E6 |
| Independent brute force | S: NumPy float64 over original vectors, 20 combinations/four per filter | W: only sampled canonical top10 independently checked; no claim all1,000 boundary sets separately brute-forced | E6:171–220; E10:419–446 |
| Plan evidence | S: 15 representative actual prepared generic plans per run | A: not EXPLAIN of every measured call; final counters strengthen linkage | E8; E11 |
| Cross-round verification | S: same code/config/data/query/truth; distinct six physical objects; actual restart each | A: distinct graphs/builds not proof of statistical independence or reproducible graph bytes | E10:874–977; E11 |
| Verifier independence | S: fresh artifact/source reads, separate summary math and NumPy distance algorithm | A: imports producer selection/recall/plan/truth helpers; common-mode code errors remain possible | E10:24–55 |
| Hashes/immutability | S: source/payload hashes, exclusive run dirs, Git snapshots, terminal API guards | W: current formatting mutation outside API; hashes detect rather than prevent edits | artifacts.py:46–172; initial diff |
| Failure preservation | S: INVALID record and traceback retained for known failures | W: in-memory observations lost if failure occurs before final workload writes | E7:838–840,969–977,1145–1177 |
| Statistical unit | S: repetition reduced within query before condition summary | High if 30k treated independent;200unique vectors,2graphs,6k repeated cells | E7:210–260 |
| Median and p95 | S: median and p95 across per-query median latencies | High if p95 called per-request tail latency; not a confidence interval | E7:249; E10:107–155 |
| Pairing/uncertainty | S: IDs retained enabling paired comparisons; rounds kept separate | M: no CIs, preregistered tests, multiplicity control or build-population inference | E12; summary.json |
| Versions/environment | S: PG17.11/vector0.8.6/Python3.12.0, pinned six Python dependencies | M: pinning source/version does not capture every compiler/hardware/scheduler effect | requirements-milestone2.txt; environment.json |
| Installation | S: checksum-pinned Postgres.app2.9.6 macOS bundle and dataset | W: Compose tag not digest/PG minor pin and Docker path not tested; cannot claim identical Docker replication | bootstrap_postgres_macos.sh; compose.yaml |
| Reproduction instructions | S: Makefile, stage configs, addendum, command record | W: README top section stale; clean-worktree gate currently blocked by dirty artifact; runtime source must be reacquired if absent | README:9–26,160–207; E13 |
| Hidden state | A: existing cluster defaults, OS cache, local environment variables and process state | Medium: fresh-machine reproducibility not independently demonstrated | postgres_local.sh; E4:29–46; SHOW ALL |

## 5. Scale-comparability verdict

**No: current 10k and 100k measurements do not isolate dataset scale.**

| Control | Corrected10k | Bounded100k | Full standalone100k |
|---|---|---|---|
| Timed unique query IDs | first5 | first20 | all200 |
| Repetitions | 1 | 2 | 5 |
| Graph builds in stage/campaign | 1 | 1 | 2 |
| Reset | shared-buffer eviction | shared-buffer eviction | real restart |
| Measured calls |75|600|30,000 total |
| Intended purpose | integration | resource/correctness qualification | one-scale characterization |
| Stage/schedule/source identity | preflight97eb5b0 | qualification5549ad1 | standalone3692827/e7952e5 |
| Time/host history | different intervals | different intervals | two successive physical rounds |

Dimension, metric, k, subset construction, labels, method SQL/settings and source
identity are comparable controls. They do not remove the differences above.
Restricting to common query IDs retrospectively helps pairing but does not
repair different caches, builds, repetitions and time/order. M1 synthetic
numbers are still less comparable: different vectors, no iterative method,
forced exact scan and a different timing definition.

The future frozen candidate in
[FUTURE_PROTOCOL_AND_CONTRIBUTION.md](FUTURE_PROTOCOL_AND_CONTRIBUTION.md)
requires a new campaign, including rerun100k, not extension/relabeling of old evidence.
No execution is authorized by that design document.

## 6. Threats-to-validity ledger

Severity: H blocks broad/causal claims; M requires scoped interpretation/control;
L is hardening. “Controlled” means at most the stated scope.

| Class / threat | Severity; controlled now? | Mitigation and semester feasibility |
|---|---|---|
| Internal: repetition/history dependence | H; observed, not controlled away | Retain first/later diagnostics; choose future timing estimand and qualify fixed preparation; feasible |
| Internal: block order and host drift | H; hash scheduling partial | Paired analysis, complementary block orders, load/thermal observations; feasible; perfect isolation not promised |
| Internal: exact/ANN resource asymmetry | M; recorded | Freeze exact memory/parallel/cost settings, inspect spill/worker evidence; feasible; equality of memory alone is not fairness proof |
| Internal: a measured query pre-executed in audit | L; disclosed | Use an existing warm-up vector in new protocol; feasible, new identity required |
| Internal: stochastic graph build | M; two rebuilds | Keep build strata; more independent rebuilds only if inferential goal/resources justify; partial semester feasibility |
| Internal: interrupted in-memory measurements lost | M; code defect remains | Incremental durable block output outside timing + interruption regression before longer runs; feasible |
| Construct: synthetic rank labels mistaken for realistic metadata | H; not realistic by design | Name controlled synthetic metadata; separately validate realistic/correlated workload if needed; feasible narrow sensitivity |
| Construct: global selectivity mistaken for local query selectivity | H; unmeasured | Exact unfiltered neighborhood enrichment and null controls; feasible offline bounded diagnostic |
| Construct: completeness mistaken for recall | H; separately measured | Present both and tie convention; already feasible/implemented |
| Construct: forced method comparison mistaken for optimizer study | H; structurally not measured | Keep claims about named paths; separate natural planner experiment only if research goal warrants |
| Construct: fixed ef40 compared as optimal ANN | H; not controlled | Say fixed configuration; fair-quality frontier needs preregistered tuning/calibration; optional later |
| External: one SIFT geometry/one100k subset | H; no broader replication | Scope conclusions; additional workload only if it tests a mechanism, not for breadth alone |
| External: one laptop/OS/version | H; explicitly limited | Record platform; clean-machine replication useful, not necessary to claim only local behavior |
| External: only single-query concurrency | M; deliberate | Exclude throughput/multi-user conclusions; concurrency experiment out of scope |
| External: periodic physical label layout/no skew | M; not varied | Declare layout; separate label permutation/cluster sensitivity; feasible but not before A5 |
| Statistical: pseudoreplication across repeats/filters/builds | H; raw IDs preserved, no formal inference yet | Query-paired reductions and build strata; never pool30k as iid; feasible |
| Statistical: p95-of-medians mistaken for request p95 | H; metric named in raw summaries | Label precisely; additional raw-request p95 must be separate estimand |
| Statistical: only two builds | H for graph-population CI | Report both; any query bootstrap conditional on observed graphs; extra builds optional |
| Statistical: post-hoc exclusion/multiple exploration | H; this diagnostic exploratory | Preserve all original calls; preregister future primary contrasts; disclose exploratory selection |
| Reproducibility: dirty historical artifact | H provenance; full runs unaffected | Preserve current bytes+Git version; user review before any restoration; do not rewrite checksum |
| Reproducibility: shared producer/verifier helpers | M; independent algorithm only for sample | Independent small toy tests and independent review; consider separate full brute-force checks before new claims |
| Reproducibility: mutable tags/local defaults | M; partial | Pin image digest if Docker is actually used; freeze relevant GUCs in new config |
| Reproducibility: checksum is not write-once protection | M; observed boundary | Read-only archival copy/Git releases plus verify-before-use; feasible |
| Reproducibility: no source commit for uncommitted review changes | L; explicit | Report base HEAD and new-file checksums; review/commit later, never mislabel as38baba3 code |

## 7. Bounded Week-7 selection: before implementation

Problem: published-in-repository condition medians hide large repetition effects
in raw timings; a reader could infer stable warmed latency from the warm-up rule.

Why now: addresses a **demonstrated** validity uncertainty before more compute.
It adds inspectable evidence for the actual midterm without pretending that
scale/correlation work has been completed.

Alternatives considered:

- Add cluster-correlated labels: relevant, but semantics/treatment validation remain undecided.
- Offline geometry/metadata diagnostic: useful next; less urgent than demonstrated timing effect.
- Run another scale: repeats an uncontrolled timing construct and violates current execution gate.
- Fix partial-evidence persistence: necessary before a future run, but does not answer the current latency question.
- Add CIs: can convey false precision while timing estimand/build uncertainty remains unresolved.
- No new work: safe; a small read-only diagnostic is justified because its inputs already exist and remain verifiable.

Chosen design: a standalone, dependency-light diagnostic with explicit new
analysis identity; input full-run payload checksums must pass, input bytes must
not change; retain both runs separately and all15conditions. Report every
repetition median and per-query first/later paired ratio, plus separately labelled
all-five versus later-four sensitivity summaries. Later-four values are not
a replacement benchmark, and no repetition is deleted.

Risks: post-hoc pattern discovery; first pass may reflect cache, scheduling,
thermal or other effects; query samples and conditions overlap. No causal
mechanism or significance will be assigned by the diagnostic.

Done criteria (now met): complete/unique input grids validated; focused synthetic tests
including paired arithmetic and mutation/overwrite refusal; both verified
full runs processed; deterministic, source-linked outputs; full suite green;
historical bytes unchanged from this audit's starting state; exact commands,
scope, failures and status recorded. No new DB measurements.

Observed diagnostic examples (existing timings, not new experiments):

| Round / condition | Median ms for passes 1–5 | Median paired first/later ratio |
|---|---|---:|
| R1 standard HNSW 50% | 17.902, 1.966, 1.621, 1.617, 1.572 | 10.877 |
| R1 standard HNSW 1% | 8.552, 1.337, 1.175, 1.011, 1.285 | 6.787 |
| R2 standard HNSW 1% | 10.135, 1.815, 1.770, 1.567, 1.479 | 5.929 |
| R1 iterative HNSW 1% | 14.008, 13.559, 14.618, 18.057, 19.771 | 0.839 |

The last example cautions against reducing every timing pattern to a uniformly
slow first pass. All 30 conditions are reported, not only these examples.
Across 6,000 method/filter/query/build cells, all five repetitions returned
identical ordered IDs; that does not turn those cells into independent samples.

## 8. Present integrity deviation

At audit start, before any write:

- HEAD: `38baba3fbf4e84dfb83d0642fe7cc067fcb748f2`.
- Only tracked modification: historical INVALID run
  `raw_results/milestone_2/20260915T184137Z_bf300f7b1133/failure.json`.
- Committed SHA256: `492635d51025cf3bb0b063bcf4474971a8f868b5df29d3e39e9d01631055d255`.
- Working SHA256: `3707e3624b10d59936c6d53de6d743e71b7346ba83f1359fdf207023d86f3e9b`.
- Parsed JSON objects are equal; only formatting changed. This audit does not
  know who or what reformatted it and does not infer malicious intent.
- That run fails its byte manifest; other seven run directories pass.
  The Sep29 academic bundle's15 payload checksums pass.
- Oct6 fresh read-only pair verification passed both full runs, including40
  fresh sampled NumPy checks and all30k stored measured calls.

Dated statements that all hashes passed on Sep29 are not statements that they
still all pass today. The current dirty file is left untouched; no original
manifest is regenerated. Operational future runs should remain blocked by the
clean-worktree gate until the owner resolves this outside historical rewrites.

## 9. Evidence register

All code locations refer to the unchanged checkpoint implementation, not prospective work.

| Key | Exact evidence |
|---|---|
| E1 | [README original question](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/README.md:5) |
| E2 | [frozen protocol configuration](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/config/milestone2/protocol.json:1) |
| E3 | [protocol narrative](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/MILESTONE_2_PROTOCOL.md:1); [standalone addendum](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/STANDALONE_100K_ADDENDUM.md:1) |
| E4 | [database implementation](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/experiments/milestone2/database.py:55) |
| E5 | [dataset selection and labels](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/experiments/milestone2/dataset.py:375) |
| E6 | [truth construction and NumPy checks](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/experiments/milestone2/ground_truth.py:17) |
| E7 | [schedule, summaries and runner](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/experiments/milestone2/runner.py:159) |
| E8 | [prepared-plan assertions](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/experiments/milestone2/plans.py:70) |
| E9 | [real restart verification](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/experiments/milestone2/restart.py:72) |
| E10 | [offline run and pair verification](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/tests/milestone2/verify_run.py:211) |
| E11 | [stored full-pair proof](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FULL_100K_PAIR_VERIFICATION.json:1) |
| E12 | [descriptive per-build full100k table](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FULL_100K_MEASUREMENTS.md:1) |
| E13 | [Sep29 checks and command record](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CHECKS_AND_COMMANDS.md:1) |
| E14 | [10k profile](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/config/milestone2/preflight-10k.json:1); [100k qualification](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/config/milestone2/qualification-100k.json:1); [full round1](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/config/milestone2/benchmark-100k-round-1.json:1); [full round2](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/config/milestone2/benchmark-100k-round-2.json:1) |
| E15 | [source manifest](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/data/sift1m/source_manifest.json:1) |
| Full R1 | [raw directory](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T171847Z_f9d4cdb50ba7) |
| Full R2 | [raw directory](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T172504Z_fa89b474a1c4) |

Files named in matrix rows (e.g. `method_sessions.json`, `executions.jsonl`,
`postgres_settings.json`) occur in both full raw directories unless a stage
is expressly specified. The entire tracked inventory/Git chronology was
inspected; detailed source/protocol review and complete offline full-run
verification are distinct from manually reading every repetitive JSON row.

## 10. Related review documents and stopping rule

- [A5 coverage, feedback closure and personal ownership](A5_COVERAGE_AND_OWNERSHIP.md)
- [Hypotheses, correlation designs, proposed future protocol and prior-art questions](FUTURE_PROTOCOL_AND_CONTRIBUTION.md)
- [Exact current verification and file-change record](VERIFICATION.md)
- [Generated repetition diagnostic](repetition_diagnostic/REPETITION_SENSITIVITY.md)

The current evidence supports successful implementation and conditional local
descriptive results. It does not support controlled scale/correlation effects,
cold-cache or steady-state claims, a novel strategy, or a finished A5 PDF/video.

Stop after this review and bounded offline diagnostic. Before any new long
benchmark: resolve provenance status, preserve partial observations on failure,
qualify the timing protocol, review literature/novelty and approve a new
campaign identity. No 250k+ execution is permitted by these files.
