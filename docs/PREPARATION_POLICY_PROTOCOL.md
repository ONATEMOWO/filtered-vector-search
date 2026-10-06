# Matched 100k preparation-policy qualification

Frozen before new timing observations on 6 October 2026. This is a bounded
measurement-validity experiment, not a new scale study or a cache-causation
experiment. The unchanged historical protocol and raw artifacts remain valid
records of their own procedures. The A5 PDF is not edited by this milestone.

## Selection rationale and historical evidence

Starting HEAD was `38baba3fbf4e84dfb83d0642fe7cc067fcb748f2`. A reviewed prior
offline diagnostic and 20 focused tests were uncommitted. The complete148-test
suite passed before adoption. These additions were preserved at `7dc2f81`.
One unrelated formatting-only change to an old invalid-run `failure.json`
remains in the original worktree; no historical payload is repaired or resealed.
This experiment uses a separate clean worktree/branch.

Candidates were (1) controlled metadata/neighborhood association, (2) more
physical scales, (3) rigorous offline reanalysis only, and (4) a matched
measurement-policy intervention. We choose4: it directly reduces uncertainty
in the latency outcome needed by every future comparison. Metadata design is
important but adds another factor before measurement interpretation is settled;
larger scales add cost without addressing that uncertainty; offline work alone
cannot test an intervention. Durability fixes and reanalysis serve this one
question, not a general harness redesign.

Observed historical standard-HNSW/50% round1 pass medians are
17.902/1.966/1.621/1.617/1.572ms. All6,000 historical query/condition/build cells
retain identical ordered results across repeats. Exploratory historical
first/later paired ratios exceed1.2 in6/30 conditions and2 in4/30; later-pass
median max/min exceeds1.2 in11/30. These are descriptive flags chosen during
inspection, not preregistered significance thresholds.

The saved prepared statements have1,022 generic and zero custom plans each.
All ten sampled exact plans show25kB in-memory top-N sorts, no temporary I/O,
and no lossy bitmap blocks. Thus generic/custom switching and exact work_mem
shortage are not demonstrated explanations. Sampled plans cannot establish
every execution's mechanism. HNSW index+heap exceeds128MiB shared buffers;
cache competition is plausible but not identified as the cause.

## Question, hypothesis and units

Question: holding data, graph, SQL, sessions' settings and schedules matched,
does adding one complete measured-query preparation pass reduce
repetition-associated latency variation relative to20 disjoint warmups alone?

Hypothesis: the added preparation reduces first/later discrepancies and
later-pass drift consistently across the two physical-build/order blocks,
without changing retrieval behavior. Lack of improvement, inconsistent effects,
or persistent drift complicates or fails this proposed remedy. Failure is a
valid outcome; no additional warmups or deleted observations are allowed after
seeing the result.

Treatment is applied to an arm execution; there are four arms in two graph
blocks, not60,000 independent treatments. The200 fixed query vectors are paired
subsamples, and five repetitions are technical repeats. Selectivities nest;
conditions and query difficulties are dependent. Report builds separately,
without significance tests or a population-of-graphs claim.

## Fixed design

- Source: pinned ANN-Benchmarks SIFT1M float32 HDF5,128D,L2,no normalization;
  SHA256 `dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984`.
- Physically load100,000 rows and build a new graph twice. Legacy SHA256 ID
  ranking, rank-mod100 metadata, query IDs and all five filters are retained.
  Counts:50,000/20,000/10,000/5,000/1,000 qualifying rows.
- PostgreSQL17.11/pgvector0.8.6; k10; m16; ef_construction64;
  ef_search40; iterative strict_order/max_scan_tuples20000/scan_mem_multiplier1.
- Exact4MB work_mem and ANN64MB are explicitly frozen; JIT off and generic
  prepared plans. Other planner/resource controls are enforced in
  `experiments/preparation/protocol.py`. No equal-resource algorithm claim.
- ArmA:20 disjoint query warmups before each method/filter block.
  ArmB:the identical20, then one full200-query exposure pass. Preparation
  durations/results are recorded separately and never mixed into measured data.
- Build1 executes A then B; build2 B then A. Block order is hash-defined and
  reversed between builds. Paired arms use identical block/query order. Query
  permutations are shared across method/filter conditions within each build.
- New persistent method sessions per arm; identical plan probes on the first
  disjoint warmup query, before all block preparations. Each probe executes the
  actual generic prepared statement twice, including EXPLAIN ANALYZE EXECUTE.
- Exactly five retained measured passes:2 builds x2 arms x3 methods x5 filters
  x200 queries x5 repeats =60,000 measurements;7,200 preparation executions;
  60 plan audits (120 probe executions). No250k+ work.

Reset policy is deliberately **CHECKPOINT plus verified shared-buffer eviction
before every arm**, with zero occupied buffers immediately after eviction.
This is not a PostgreSQL restart and does not flush the OS cache. Do not use
historical restart-based runs as controlled comparison arms. Same graph OIDs,
filenodes and cluster identity must persist between paired arms; all six
table/index identities must change between physical builds. Reject concurrent
client sessions around resets and use a campaign advisory lock. Background
server/OS work, OS-cache carryover, host thermal state and two-build limitations
remain. AC power is required at boundaries. No cache-residency guarantee.

ArmB changes both prior work volume and query familiarity. The estimand is the
whole operational preparation policy. An equal-work disjoint-query treatment
would be needed to isolate familiarity; that is outside this milestone.

## Measurements, analysis and decisions

Timing uses the existing monotonic `perf_counter_ns` around the same prepared
execute+fetch whose results are scored. Connection setup, plan auditing,
serialization, scoring and persistence are outside that interval. Journal
flushes occur between passes in both arms and may still affect subsequent
machine state; this is a matched new protocol, not literal historical replay.

Per build/arm/method/filter report:

1. Five pass medians and p95s of individual execution latency within each pass.
2. Median and p95 across the200 per-query medians of all five repetitions.
   This p95 is not an individual-request-tail p95.
3. Median over queries of first duration / median(repetitions2..5), and median
   absolute log2 of those paired ratios (zero is no discrepancy).
4. Largest/smallest pass median among passes2..5.
5. Engineering flag: any pass median divided by the median over queries of
   their later-four medians outside[0.8,1.2]. This predeclared20% tolerance is
   a diagnostic choice, not a statistical test or proof of steady state.
6. Paired B/A per-query all-five median ratios, preparation cost, result-order,
   recall and completeness comparisons. No cross-build timing pooling.

For each method/filter, directional support requires B to strictly reduce both
median absolute log2 first/later discrepancy and later-pass median range in
**both** builds. Report the actual effects and every failure; do not convert
that rule into a general causal claim. Candidate operational acceptance
additionally requires no engineering flags in either B build and unchanged
quality. Even acceptance would be local evidence, not universal stability.

## Correctness, durability and reproducibility gates

Retain source checksum/shape/dtype/finite checks, full database/source stream
equality, exact filter counts/vector dimensions/index parameters,1,000 exact
truths plus deterministic reexecution and20 NumPy checks per build. Truth
supports canonical and tie-aware recall. Exact must return10 at recall1;
ANN shortfalls are outcomes, not validation failures. Compare both arms on
the same graph without requiring identical answers across different builds.

Plans must show the intended paths and settings. Each prepared statement must
have exactly1,022 generic uses inA or1,222 inB and zero custom uses. Save all
raw execution IDs/distances/durations, query orders, hashes, settings, identities,
host snapshots, plans and failures. Independently reconstruct the matrix,
scores, preparation schedule, counters, chunk coverage and source provenance.

Exclusive fsynced chunks persist after every completed preparation/repetition
batch. On a caught interruption, preserve the active completed-row prefix;
on an uncatchable kill, at most the active batch may be lost. No zero-loss
claim. Completed chunks remain inspectable after failure, and terminal success
is written only after producer gates; independent validation is required before
accepting/committing empirical evidence. Existing run directories are never
overwritten. Launch from clean committed source, and preserve the starting
322-file hash inventory in `outputs/preparation_policy_20261006/STARTING_STATE.json`.

## Focused primary-source rationale

PostgreSQL17 documents [generic-plan control](https://www.postgresql.org/docs/17/sql-prepare.html),
[EXPLAIN execution/instrumentation](https://www.postgresql.org/docs/17/sql-explain.html),
and the [OS-cache limits of I/O statistics](https://www.postgresql.org/docs/17/monitoring-stats.html).
[pg_prewarm](https://www.postgresql.org/docs/17/pgprewarm.html) does not protect
pages from subsequent eviction. [Pinned pgvector0.8.6](https://github.com/pgvector/pgvector/tree/v0.8.6)
documents postfiltering and bounded iterative scanning. These sources support
controls and interpretation, not a novel discovery claim.
[ACORN](https://arxiv.org/abs/2403.04871) and a
[pgvector planner study](https://arxiv.org/abs/2602.11443) already address
predicate/vector relationships and query optimization. Correlation remains a
useful future axis, not an established novelty claim for this project.

## Stop

Complete this fixed campaign, independent verification and conservative
interpretation. A negative or mixed policy result is a stable checkpoint.
Do not tune until green, rerun selectively, expand scales, change metadata,
edit A5, or automatically launch a second intervention.

## Reproduction commands

Use the pinned Milestone 2 environment and dataset documented in README. Launch
only from a clean committed worktree on AC power, with the project PostgreSQL
instance running and no other client sessions. This command recreates only the
two `milestone2.sift_*` benchmark tables and their indexes. It does not modify
Milestone 1 tables or historical result directories.

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.preparation.runner --config config/preparation-policy-v1.json
```

The runner prints the newly created run directory. Substitute that actual path
for `RUN_DIRECTORY` below. Verification is offline and reads the pinned source
HDF5; its output should be preserved outside the finalized raw directory.

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.preparation.verify RUN_DIRECTORY
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m analysis.preparation_policy pilot RUN_DIRECTORY --output outputs/preparation_policy_20261006/pilot_analysis
```

Historical reanalysis is a separate, non-comparative context artifact:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m analysis.preparation_policy historical raw_results/milestone_2/20260929T171847Z_f9d4cdb50ba7 raw_results/milestone_2/20260929T172504Z_fa89b474a1c4 --source .runtime/datasets/sift-128-euclidean.hdf5 --output outputs/preparation_policy_20261006/historical_analysis
```

Analysis outputs are exclusive: reproduction must use a new output directory.
Do not run analysis/tests during measured database execution. Completed raw
data must pass the independent verifier before interpretation or evidence
commit. A producer COMPLETE marker alone is insufficient for acceptance.
