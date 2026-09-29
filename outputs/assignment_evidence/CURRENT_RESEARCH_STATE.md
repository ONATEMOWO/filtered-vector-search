# Current research state — 29 September 2026

This checkpoint is factual progress evidence, not final research conclusions.

## Completed and verified

- Preserved the original uncommitted work and history before editing; resumed
  from `0f5fe348813934e9f93ccb483be2979feac59d8c` without resetting/reconstructing.
- Corrected and committed the harness, including the strict preflight profile,
  single-bound-vector query, actual prepared-generic-plan audits, independent
  source/ground-truth verification and immutable finalization.
- 128 automated tests passed, with Python compilation, dependency checks,
  shell syntax checks and whitespace validation passing.
- Corrected 10k preflight: 75 timings, 300 warm-ups, 1,000 ground truths and
  identical re-executions, 20 independent brute-force checks, 15 valid plans.
- Physical 100k qualification: 600 timings and the same full validation gates.
  A permission-blocked prior attempt was preserved separately and not counted.
- Full standalone 100k round 1 completed and independently verified:
  `20260929T171847Z_f9d4cdb50ba7`, 15,000 timings, all 200 selected queries,
  five repetitions per condition, a fresh graph and a verified real restart.
- Three generated qualification figures and a machine-derived measurement
  table link to source checksums. No screenshot or final finding is claimed.

## Full 100k completed and independently verified

Round 2 `20260929T172504Z_fa89b474a1c4` also passed its 15,000-execution run.
The independent pair verifier rechecked **all 30,000 measured executions**,
both sets of 1,000 exact ground truths, all 30 plans, 600 warm-ups and 40 fresh
NumPy combinations. Its checksums were unchanged before/after verification.
Source code/configuration, selected data, queries and ground-truth content
matched across rounds. All six physical table/index identities changed between
rounds; the HNSW index OIDs were **24649** and **24677**. Each round separately
proved an actual later postmaster start with the same cluster/physical objects
across that restart. Exact results were complete with recall one in both.

The immutable rounds are committed as `e7952e5` and `f671005`; the latter also
contains the independent pair proof. Full-round totals were 290.482 s and
317.749 s, including operator restart waits of 32.639 s and 61.384 s.
The two complete rounds therefore took about 10.14 minutes before final
artifacts, or 8.57 minutes excluding those waits, not including the later
independent verifier and report preparation.

Selected **descriptive 100k-only observations**, not final findings:

| Method/filter | Round 1 median ms | Round 2 median ms | Canonical recall R1 / R2 | Returning 10 R1 / R2 |
|---|---:|---:|---:|---:|
| Exact 50% | 26.524 | 27.623 | 1.0000 / 1.0000 | 100% / 100% |
| Standard HNSW 50% | 1.901 | 1.406 | 0.9635 / 0.9635 | 99.5% / 99.5% |
| Iterative HNSW 50% | 1.721 | 1.351 | 0.9635 / 0.9635 | 100% / 100% |
| Exact 1% | 2.088 | 2.440 | 1.0000 / 1.0000 | 100% / 100% |
| Standard HNSW 1% | 1.395 | 1.854 | 0.0420 / 0.0420 | 0% / 0% |
| Iterative HNSW 1% | 15.852 | 15.581 | 0.9835 / 0.9835 | 100% / 100% |

Full summaries, including tie-aware recall, are in `FULL_100K_MEASUREMENTS.md`.
The iterative 50% tie-aware mean is 0.9640 in each round; completeness is not
the same as recall. No poor or unusual measurements were selectively removed.

## Unfinished work

No 250k+ execution has run. Literature/novelty review, larger-scale protocol
review, final statistical analysis and final research conclusions remain
unfinished. Operational correctness at 100k is demonstrated; scientific
approval to proceed to larger scales has not been granted by this evidence.

## Evidence entry points

- [A3 factual evidence](A3_FACTUAL_EVIDENCE.md)
- [A4 factual evidence](A4_FACTUAL_EVIDENCE.md)
- [Qualification measurements](VERIFIED_MEASUREMENTS.md)
- [Full 100k measurements](FULL_100K_MEASUREMENTS.md)
- [Independent pair proof](FULL_100K_PAIR_VERIFICATION.json)
- [Complete factual handoff](MILESTONE_2_FACTUAL_HANDOFF.md)
- [Checks and commands](CHECKS_AND_COMMANDS.md)
- [Chronological commit history](COMMIT_HISTORY.md)
- [Exact changed-file inventory](FILE_INVENTORY.md)
- [Video evidence guide](VIDEO_GUIDE.md)
- [Scoped full-100k protocol](../../docs/STANDALONE_100K_ADDENDUM.md)

The qualification figures use 5 timed queries at 10k and 20 at 100k; they must
not be interpreted as a controlled full-query scale comparison. The standalone
100k campaign is not the original four-scale ascending/descending campaign.

## Next steps and stopping rule

Stop before 250k+ for literature/novelty and protocol review. Decide whether
the single-scale campaign should be exploratory evidence or whether a new
complete ascending/descending multi-scale campaign is needed. Review cache,
host variability and resource projections before authorizing more compute.
The local PostgreSQL server is left running with the last 100k scale; Milestone
1 tables remain intact. No benchmark process is left running.
