# Hypotheses, future protocol, and contribution review

Review date: 6 October 2026. Evidence checkpoint: `38baba3`.

This is a research-design review, not assignment prose, an accepted protocol,
an execution authorization, or a claim of novelty. No experiments described
below were executed for this document. Existing results retain their original
protocol identities and metadata semantics.

The sole selected bounded Week-7 implementation is an offline analysis of
repetition/order sensitivity in the already verified full-100k runs. The audit
found substantial first-pass timing differences despite the existing warmups.
That observed threat has priority over implementing correlated metadata or
collecting more benchmark timings. Correlation diagnostics below remain future
work. The 250k, 500k, and 1M execution gate remains closed.

## Evidence anchors and scope

- [Original frozen design](../../docs/MILESTONE_2_PROTOCOL.md) and
  [protocol values](../../config/milestone2/protocol.json).
- [Standalone-100k amendment](../../docs/STANDALONE_100K_ADDENDUM.md).
- [Metadata and query selection](../../experiments/milestone2/dataset.py):
  `build_scale_manifest`, `select_query_ids`, and the pinned global ordering.
- [Search SQL and session settings](../../experiments/milestone2/database.py):
  `search_sql`, `COMMON_SESSION_SETTINGS`, and `METHOD_SESSION_SETTINGS`.
- [Scheduling and aggregation](../../experiments/milestone2/runner.py):
  `build_schedule` and `summarize_executions`.
- [Full-100k observations](../assignment_evidence/FULL_100K_MEASUREMENTS.md)
  and [independent pair proof](../assignment_evidence/FULL_100K_PAIR_VERIFICATION.json).

Implemented scope is a named-access-method comparison on SIFT vectors, with
synthetic metadata, L2 distance, k=10, fixed HNSW parameters, and one local
machine. Forcing HNSW on one table while allowing natural exact plans on another
does not test an unconstrained PostgreSQL routing policy. Passing correctness
tests does not prove realism, causal attribution of every latency difference,
student conceptual ownership, or general scientific validity.

## Hypotheses and mechanisms

The observations in this table are descriptive results from the two complete
100k rounds. They are not independently replicated experiments at every scale.

| Hypothesis | Mechanism and revised scope | Current evidence | Missing evidence and confounders | Falsifier / required experiment |
|---|---|---|---|---|
| H1: restrictive filters degrade standard HNSW | Split qualifying-result yield/completeness from Recall@10. A fixed candidate stream contains fewer qualifying rows under a narrower nested predicate. Recall need not be individually monotonic because filtered ground truth changes. | Standard mean recall falls from 0.9635 at 50% to 0.042 at 1% in both rounds; completeness falls from 99.5% to 0%. | One scale, metadata realization, and search budget; nested filters and repeated queries are dependent. Candidate-stream constancy is a condition, not a measured universal guarantee. | Under independently assigned labels and fixed graph/settings, no aggregate yield decline beyond uncertainty challenges the expectation. Test paired queries, returned counts, and recall separately. A single nonmonotonic recall pair does not refute the narrower yield mechanism. |
| H2: iteration recovers qualifying neighbors at a cost | Continuing a post-filtered scan can find additional qualifying vectors, subject to tuple/memory limits. Strict result ordering is not an exact-neighbor guarantee. | At 1%, iterative mean recall is 0.9835 with 100% completeness; standard recall is 0.042 with 0% completeness. Iterative median latency is higher in both rounds. | Latency is not a direct count of search work. Cache/order effects, stopping behavior, and limits confound a universal cost claim. Complete results can still miss exact neighbors. | A correctly configured continuation with no yield improvement challenges the mechanism in that condition; failure to return k disproves guaranteed completeness. Compare yield, recall, latency, plan evidence, and budget exhaustion separately. |
| H3: exact becomes cheaper with fewer qualifying rows | Reduced candidate counts reduce distance/sort work, but heap-page visits, fixed overhead, parallelism, and plan changes can prevent monotonic latency. | Exact median latency increases monotonically with match rate in both observed full rounds. | Bitmap versus sequential/parallel plans, locality, cache, work_mem, and execution order. | Persistent slower exact latency for smaller sets falsifies a strict monotonic-latency claim, not the weaker candidate-work mechanism. Preserve plan and buffer evidence and assess paired query changes. |
| H4: scale shifts the exact/ANN crossover | Scale changes candidate counts, graph behavior, and memory/cache residency. A fixed absolute iterative limit also covers a different fraction of N. | Not established. The two complete benchmark rounds are both 100k. | Different sample sizes, reset policies, schedules, and purposes make 10k/100k qualification comparisons unsuitable as a controlled scale study. | Run a new frozen multi-scale campaign. An unchanged quality-eligible method ranking across tested scales does not support a shift; it is not proof of scale independence everywhere. |
| H5: correlation matters at fixed selectivity | Local enrichment/depletion of qualifying neighbors changes the yield available to post-filtered graph search even when global match count is identical. | Not tested. Current generation is content-blind, not empirically proven independent of every query neighborhood. | Corpus clustering differs from query–predicate alignment. Label cardinality, graph rebuilds, physical row layout, query choice, and anchor selection can confound effects. | First establish an achieved correlation contrast independently. If strong contrasts produce negligible paired outcome differences within preregistered margins, H5 is unsupported in that domain. |
| H6: no universal threshold | Replace the unbounded claim with: a selectivity-only rule may have higher quality violations or latency regret than a rule also using scale/locality within a declared workload. | Untested. Existing observations motivate this question but do not validate a router. | Oracle features, training/test leakage, post hoc target choice, limited graph builds, and domain shift. | Freeze rules, targets, and material-regret margins before held-out evaluation. Equal held-out performance favors the simpler rule over the tested domain. Finite experiments cannot prove universal nonexistence of a threshold. |

An illustrative null model is X ~ Hypergeometric(N, sN, c), where c is an
actually exposed candidate count and s is global match rate. Expected yield is
cs. This is a modeling assumption, not a statement that ef_search=40 means
exactly 40 graph visits or distance calculations. The pinned extension documents
ef_search as the candidate-list size; its iterative tuple limit is approximate
and does not include the initial scan. These distinctions must survive into any
cost model. See the [pgvector 0.8.6 documentation](https://github.com/pgvector/pgvector/blob/v0.8.6/README.md#iterative-index-scans).

Latency comparisons should show quality alongside speed. A fast method that
returns too few rows is not automatically preferable. A quality-constrained
"crossover" additionally requires a declared target: for example, a specified
population-mean recall and completeness rate. This review does not choose a
target retrospectively to make one observed method win. Per-query Recall@10 is
discrete; a requirement greater than 0.9 effectively requires all ten neighbors
for that query, unlike a mean-recall target over queries.

## Correlation: construction is not validation

There are two distinct constructs:

1. Corpus metadata–geometry association: do neighboring base vectors tend to
   have similar metadata?
2. Query–predicate alignment: does a particular query's neighborhood contain
   more or fewer qualifying vectors than its global match rate predicts?

A cluster label may enrich queries near that cluster and deplete queries far
from it. Calling all cluster-derived predicates "positive correlation" is
incorrect. Synthetic cluster labels also do not become realistic business or
semantic metadata merely because a clustering algorithm produced them.

| Model | Construction | Hold selectivity constant | What remains artificial / ambiguous |
|---|---|---|---|
| Independent/content-blind | Permute a fixed bucket multiset using an independent recorded hash domain or seeded permutation. Preserve the historical rank-mod-100 mode unchanged. | Exactly equal bucket counts and identical threshold counts. | One deterministic assignment is one realization; absence of vector input is not proof of zero realized local association. |
| Cluster-aligned | Fit a frozen base-only clustering; assign labels from cluster membership or a declared cluster/within-cluster ordering. | Raw cluster IDs usually have unequal frequencies. Use explicit quotas or quantile ranks and report their geometric effect. | Number of clusters, fitting sample, initialization, unequal cluster sizes, and partial-cluster selection affect the construct. |
| Neighborhood-local | Rank vectors by distance to fixed base-derived anchors, or use a preregistered local-neighborhood score. | Quantize the rank into 100 equal-sized buckets at fixed N. | Anchor choice and query–anchor proximity define a synthetic workload. Selecting anchors based on measured ANN outcomes leaks evaluation information. |
| Anti-aligned | Select equally sized predicates depleted from query neighborhoods, keeping the query IDs fixed. | Same qualifying cardinality as the aligned/null conditions. | Reversing label numbers alone does not guarantee negative alignment for all queries. Deliberately distant predicates are stress cases, not evidence of typical usage. |
| Graded | Apply a frozen membership-preserving swap schedule to aligned labels, or blend ranked geometry and noise scores before re-ranking. | Swaps preserve label marginals; quantiles preserve exact threshold counts. | The mixing parameter is not achieved correlation strength. Intermediate assignments need independent diagnostics. |

A bounded future sensitivity study can use a geometry-score ordering, with
stable ID tie-breaks, and quantize it into equally sized buckets. A permutation
of the same bucket multiset is the null treatment. Multiple preregistered
anchors/assignments avoid presenting one convenient realization as general.
Use new mode/config names; never change historical `filter_bucket` semantics.

Required diagnostics, computed outside benchmark timing:

- Verify exact marginal counts, predicate nesting, unchanged vector/ID values,
  deterministic generation, and metadata-manifest hashes.
- For fixed unfiltered-neighborhood sizes L = 40, 100, and 1000, compute
  p_local(q,L) = count(qualifying exact unfiltered neighbors)/L and enrichment
  e(q,L) = p_local(q,L)/s. Retain query-level distributions, not only an average.
- Compare with count-preserving label-permutation envelopes using a frozen
  replicate count, seed/domain, and summary statistic. This is a diagnostic
  null, not a population-level realism certificate.
- At 1% and L=40, observing zero positives can occur frequently under the null;
  do not label every such query "anti-correlated" without that reference.
- Use independently computed unfiltered neighborhoods, not the approximate
  candidates produced by the very method under evaluation.
- Report anchor distance and, where appropriate, label agreement along sampled
  neighbor edges with a marginal-frequency baseline.
- Treat failure to create the intended correlation contrast as an unsuccessful
  treatment, not a reason to keep changing the generator until results agree
  with the hypothesis. Preserve failures.

These diagnostics are not proposed as a new metric. Prior work already uses
query–predicate alignment and local/global selectivity, as recorded below.

### Metadata across nested scales

There is a real design trade-off:

- One globally fixed geometry-derived labeling preserves each vector's label
  but generally gives only approximately equal match rates in reduced subsets.
- Requantiling independently at each scale gives exact rates but changes some
  vectors' metadata as N changes.
- A declared shell-balanced assignment over the four nested scale intervals
  can preserve exact counts at planned boundaries and stable per-vector labels,
  but introduces shell-specific geometric quantiles.

Do not claim all three properties without a construction and tests. The first
multi-scale baseline below avoids this additional factor by keeping the legacy
rank-mod-100 semantics. Any correlation × scale study needs a separate accepted
design rather than silently enlarging the baseline.

## Frozen candidate design version `multiscale-baseline-candidate-v2-20261006`

**Status: review candidate, not accepted and not executable authorization.**
"Frozen" means the exact proposal here is versioned for review. Any change
after pilot evidence requires a new version and explicit acceptance before
full execution. Existing configurations remain unchanged and larger-scale
execution remains disabled.

### Why a new campaign is necessary

The 10k preflight timed five queries once; 100k qualification timed twenty
queries twice; full 100k timed two hundred queries five times in each of two
builds. Qualification used PostgreSQL-buffer eviction, while full 100k used
actual restarts. Their stage-specific schedules and purposes also differ.
They are not interchangeable samples in a scale regression. Comparing only the
five common query IDs would remain exploratory because these other differences
persist.

The new campaign must rerun 100k alongside the other three scales. Standalone
100k remains historical descriptive evidence and a pilot source, not the first
cell of a silently appended multi-scale experiment.

| Control | Fixed candidate choice |
|---|---|
| Dataset / identity | Existing pinned ANN-Benchmarks SIFT1M HDF5, unchanged float32 values, same SHA-256 and little-endian ID-order digest. No normalization. |
| Physical scales | 100,000; 250,000; 500,000; 1,000,000. Each physically loaded with its own freshly built graph; never simulate scale using a predicate over a larger graph. |
| Subset / insertion order | Same global SHA-256 ID ranking and prefix subsets; rank order retained for both tables. |
| Metadata | Legacy `filter_bucket = scale_rank % 100`; thresholds 50, 20, 10, 5, 1. Exact counts at every planned N; nested groups explicitly acknowledged. No correlation factor in this baseline. |
| Query identities | The same pinned 200 measured query IDs and next 20 disjoint warmup IDs for every scale, method, filter, and build. No outcome-driven reselection. |
| Metric / k | PostgreSQL `vector(128)`, L2 `<->`, k=10. |
| Software | PostgreSQL 17.11, pgvector 0.8.6, and pinned Python dependencies. No version upgrade during the campaign. |
| Exact path | Metadata B-tree, no vector index, normal planner scan choices. Exact `work_mem=4MB` explicitly fixed to the observed baseline instead of inherited silently. |
| ANN paths | Same HNSW-only vector-order route assertions; `m=16`, `ef_construction=64`, `ef_search=40`, `work_mem=64MB`; iterative off versus strict_order; `max_scan_tuples=20000`, `scan_mem_multiplier=1`. |
| Common/system settings | JIT off; force_generic_plan; statement_timeout=120s; shared_buffers=128MB; max_parallel_workers_per_gather=2, explicitly checked. Other server settings captured and held unchanged. Different actual worker launches remain observable variability. |
| Build settings | maintenance_work_mem=1GB; max_parallel_maintenance_workers=0. Preserve insertion order and record each new physical build identity. No claim of a user-settable HNSW construction seed. |
| Replication | Five retained timed passes per query/condition/build. Two new builds at each N: ascending scale order in round A, descending in round B. This is limited build replication, not a precise estimate of construction-randomness variance. |
| Preparation | After load/build/vacuum/ground-truth checks, actual PostgreSQL restart verified by server/cluster/physical identities. No OS cache flush claim. Before each block: 20 disjoint warmups, then one untimed full pass over all 200 measured queries, then five retained passes. |
| Plan probes | Audit the actual prepared generic statement using the first fixed disjoint warmup query, not a measured query. Probe outside timing, before the declared warmup sequence. Preserve settings, path, ordering, counters, and row evidence. |
| Timing | Persistent connections; one query active; perf_counter_ns around prepared execute plus complete fetch. Preparation, scoring, EXPLAIN, and artifact writes excluded. |
| Correctness | Per-scale/filter/query exact tie-aware truth, complete deterministic reexecution, at least 20 independent stratified brute-force checks, all measured-row validation, checksums and immutable directories. At 1M validate unfiltered neighbors separately against the supplied SIFT ground truth. |
| Evidence | Separate run/build identity, raw integer timings, row IDs/distances, recalls, completeness, warmup/preparation records, plans, phase times, resource snapshots, failures, source/config hashes, and verification proof. |

Explicitly fixing exact work_mem=4MB and ANN work_mem=64MB reproduces the
observed method configurations; it is not an equal-memory comparison. Exact
parallelism is allowed as part of the realistic PostgreSQL baseline. If a
single-worker or equal-memory comparison becomes necessary, it is a separate
sensitivity experiment with a new identity, not a silent change.

The added full-query preparation pass is a proposal responding to observed
first-pass sensitivity. It may deliberately reuse the measured query vectors;
therefore call the workload **fixed prepared-query operational measurements**,
not unseen-query latency, cold-cache latency, or guaranteed steady-state latency.
All preparation executions must be logged separately and never included in the
five timed repetitions. Merely adding one pass does not prove stability.

Additional explicitly frozen baseline server values: max_parallel_workers=8,
max_worker_processes=8, effective_cache_size=4GB, seq_page_cost=1,
random_page_cost=4, cpu_tuple_cost=0.01, cpu_index_tuple_cost=0.005,
cpu_operator_cost=0.0025, effective_io_concurrency=0, autovacuum=on,
huge_pages=try. These are the recorded full-round baseline, not recommended
universal tuning. Capture settings after each restart and assert these values;
record actual worker launches and any maintenance contention. The full SHOW ALL
snapshot remains evidence, not a claim that every setting is performance-neutral.

### Paired schedule and stability gate

- Freeze a campaign schedule before running it. For a given build, use the
  same method/filter block order at every scale; use its reverse in the second
  build. This reduces a scale-by-block-position confound without claiming all
  carryover effects are removed.
- For each `(build, filter, repetition)`, use the same hash-shuffled query order
  across methods and scales. Remove method, scale, and stage identity from this
  permutation's domain; preserve the complete schedule artifact. Preparation
  uses a separately frozen permutation of the same 200 IDs.
- Before authorizing this matrix, run only a separately approved 100k stability
  pilot. Compare every retained pass with the median of passes 2–5 within each
  method/filter block. Define B = median across queries of their median latency
  over passes2–5 and M_r = median latency across queries in pass r. A candidate
  material-drift gate is any M_r/B outside [0.8,1.2]; retain query-paired ratios and inspect late-pass trends
  as well. This threshold is a review choice, not a discovered natural constant.
- Any condition crossing the gate requires diagnosis and a new protocol
  version or an explicitly justified decision to study order-sensitive latency.
  Do not discard a troublesome first timed pass after examining it or run
  adaptive extra warmups only for inconvenient conditions.
- Passing the pilot establishes only adequacy under its conditions. Repeat the
  same drift diagnostics for every full scale/build; flag affected cells and
  preserve their evidence rather than silently declaring them steady-state.

The baseline matrix is 120,000 retained timings. Fixed per-block preparation is
220 executions × 15 blocks × 8 scale/build combinations = 26,400 separately
logged preparation executions, in addition to plans and truth validation.
Two builds and reverse ordering reduce some bias but do not guarantee immunity
to background load, thermal drift, OS caching, or graph variability.

### Analysis and resource boundaries

- Reduce five repetitions to one query-level latency summary per condition and
  build before population summaries. Preserve pass-specific distributions as
  a sensitivity analysis; do not treat 120,000 rows as independent samples.
- Pair comparisons by query ID within build/scale/filter. Report the two builds
  separately and show their variation. Query-resampling intervals, if later
  preregistered, are conditional on these observed graphs and query-sampling
  assumptions. Two builds do not justify strong general graph-level inference.
- Existing p95 is the percentile of per-query median latencies, not the p95 of
  all individual requests. Retain accurate labels for both if both are added.
- The fixed absolute iterative cap is deliberately held constant, not a fixed
  fraction of N. Any resulting scale behavior includes that policy choice.
- Keep AC/energy policy fixed, record background activity and memory/disk state,
  and reserve a quiet run window. A "no unrelated workload" intention is not
  proof that the laptop had no competing OS/app work.
- Perform per-stage resource review, starting at 100k; keep the existing 120s
  statement timeout. No computed linear resource projection is permission to
  proceed through swapping, disk exhaustion, or memory pressure. Pause on
  abnormal resource pressure, preserve the attempt, and re-review before retry.
- Use bounded vector chunks for independent checks, not a dense all-pairs
  matrix. New memory-heavy tooling is not required to carry out this design.
- Before any 250k+ execution, require explicit protocol/literature acceptance,
  a passing stability pilot, and a documented resource budget. This document
  does not satisfy or bypass that authorization gate.

## Separate, conditional 100k correlation sensitivity

After the baseline timing threat is understood, a narrowly scoped study could
compare legacy content-blind labels with a new null/geometry-aligned treatment
at 100k. First validate selectivity and achieved correlation offline. Freeze
metadata/query pairing, treatment-generation choices, analysis, and budgets
before any database measurement. Hold graph/vector/insertion effects constant
where possible; if treatments require rebuilds, use balanced treatment order
and paired build replication and report the residual graph confound.

This is not authorization to modify current tables, extend the full matrix,
replace historical metadata, or claim real-world behavior. A full selectivity
× scale × correlation factorial is not the default semester plan.

## Contribution levels and semester feasibility

| Level | Scientific value | Novelty risk / evidence needed | Feasibility and publication threshold |
|---|---|---|---|
| A: rigorous characterization | Carefully verified, version-specific description of exact/standard/strict iterative trade-offs. | Known mechanisms already predict many outcomes. Need controls and truthful scope, not merely passing tests. | Strong class project. Publication needs a substantive new observation, useful reproducibility result, or consequential implementation-specific gap. |
| B: selectivity × scale × correlation | Tests interactions hidden by global match rate. | Prior research explicitly studies these factors. Need validated treatments, independent realizations/builds, interaction analysis, and preferably a real-metadata workload before broad claims. | A bounded sensitivity study is feasible; an exhaustive factorial risks breadth without validity. |
| C: decision surface | Makes method choice and quality constraints explicit. | A winner plot is not a validated optimizer. Need declared quality eligibility, uncertainty, held-out conditions, and clear treatment of incomplete output. | Feasible descriptive extension; publication needs transferability or a new defensible mechanism rather than a hardware-specific chart. |
| D: routing policy | Could reduce latency relative to always-exact or always-ANN choices. | Strong overlap with adaptive hybrid-search planning. Include feature/routing cost, fallback, quality violations, oracle and simple-rule baselines, and held-out evaluation. | Optional stretch only after characterization. A hard-coded threshold fitted to these same queries is not evidence of a useful general policy. |
| E: cost/quality model | Predicts cost and selects a strategy subject to a declared quality target. | Direct prior overlap; mean recall prediction is not a per-query guarantee. Need calibrated non-oracle features, constrained evaluation, domain-shift checks, and comparable models. | Probably beyond the safe core this semester. Publishability requires demonstrable novelty and robust benefit over existing approaches. |

Recommended core remains A, with a carefully justified B sensitivity if time
and controls permit. A descriptive C surface can follow; D/E are hypotheses
about possible future contributions, not current accomplishments.

## Limited primary-source scan and overlap

Screening performed 6 October 2026. This is not an exhaustive systematic
review, and does not establish novelty or absence of prior work. Published or
preprint claims below are distinguished from this review's inference.

| Primary source | What the source establishes or studies | Relevance / inference for this project |
|---|---|---|
| [ACORN, SIGMOD 2024](https://arxiv.org/abs/2403.04871), [author-hosted paper](https://petereliaskraft.net/res/acorn.pdf) | Explicitly examines selectivity, dataset size, and query correlation; formalizes query–predicate alignment and proposes predicate-subgraph traversal. | Generic Level-B framing is already prior art. A new pgvector characterization must identify a narrower question rather than claim discovery of correlation effects. |
| [Filtered-DiskANN, 2023](https://harsha-simhadri.org/pubs/Filtered-DiskANN23.pdf) | Discusses limitations of fabricated/random labels and includes shuffled-label experiments. | Count-preserving label controls and concern for real metadata are established ideas, not novel contributions here. |
| [Amanbayev et al., 2026 preprint](https://arxiv.org/html/2602.11443v1) | Studies database-level filtered search, pgvector plan choice, and global/local selectivity; reports PostgreSQL16/pgvector0.8.1. | Strong overlap with characterization and decision surfaces. No occurrence of "iterative" was found in the retrieved text; that is a lead for deeper artifact review, not proof of a novelty gap. |
| [Shi et al., 2025 preprint](https://arxiv.org/abs/2509.07789) | Proposes a unified filtered-ANN benchmark and emphasizes parameter coupling, query difficulty, selectivity, and scalability. | Fixed-setting comparisons answer a bounded question; claims about algorithm superiority require fair quality/tuning considerations. |
| [E2E, v2, accepted KDD 2026](https://arxiv.org/abs/2602.06721v2) | Estimates filtered-search effort from early probing and uses adaptive termination. Its initial title was Filtered Approximate Nearest Neighbor Search Cost Estimation. | Cost/correlation-aware optimization has direct prior overlap; D/E novelty cannot be presumed. |
| [Filtered Vector Search tutorial, 2025](https://research.google/pubs/filtered-vector-search-state-of-the-art-and-research-opportunities/) | Reviews filtering strategies, correlation/cardinality effects, iterative post-filtering, and recall challenges. | Useful orientation and vocabulary; not validation of this project's results. |

### Questions requiring deeper literature/artifact research

1. Which studies isolate standard versus strict iterative pgvector scans and
   report incomplete-result rates as distinct from Recall@k?
2. Which extension versions, limits, planner freedoms, and graph settings were
   used? Did implementation changes alter their conclusions?
3. Do published correlation models control global selectivity, query–predicate
   alignment, and per-vector metadata identity across scales separately?
4. Which studies use real metadata and what realistic failure modes cannot be
   represented by SIFT plus invented labels?
5. Are claimed crossover thresholds quality-constrained, or comparisons between
   a fast incomplete output and an exact complete output?
6. How are graph construction, repeated queries, warmup, OS caching, and pass
   order handled? Are uncertainties conditional on one graph or multiple builds?
7. Can local correlation be estimated cheaply without an exact-neighbor oracle,
   and is that feature cost included in any routing benefit?
8. Which adaptive/routing policies preserve quality under held-out predicates,
   unseen queries, scale changes, and different datasets?
9. What exact-search candidates and metadata-index strategies do existing
   systems compare against? Are planner errors separated from forced-path costs?
10. After reading source artifacts rather than abstracts alone, what narrow,
    consequential pgvector-specific question remains unanswered?

## Ownership questions for the researcher

- Why can returning ten qualifying rows still yield recall below one?
- Why does strict ordering not make HNSW exact?
- What does ef_search control, and what does it not count?
- Why can a restrictive filter make exact search competitive?
- Why are repetitions and nested predicates not independent query samples?
- Which caches does PostgreSQL restart reset, and which remain uncontrolled?
- What is different about the current content-blind labels, corpus clustering,
  and a query–predicate correlation treatment?
- Why can supplied SIFT top-100 neighbors not replace filtered/subset truth?
- What can forced HNSW plans establish, and why do they not demonstrate
  PostgreSQL optimizer quality?
- What exactly changed between pipeline validation and the full 100k campaign?
- Which design/code decisions were AI-assisted, and can the student independently
  explain, reproduce, challenge, and modify the relevant logic?

Being able to answer these questions is distinct from possessing a repository
whose tests pass. Neither tests nor this document establish conceptual ownership.
