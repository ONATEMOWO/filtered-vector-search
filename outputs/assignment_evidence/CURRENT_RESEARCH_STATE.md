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

## Pending at this intermediate checkpoint

The second full 100k round and cross-round verification have not yet completed.
This file will be updated after that stage. No 250k+ execution has run.
Literature/novelty review, larger-scale protocol review and final statistical
analysis remain unfinished.

## Evidence entry points

- [A3 factual evidence](A3_FACTUAL_EVIDENCE.md)
- [A4 factual evidence](A4_FACTUAL_EVIDENCE.md)
- [Qualification measurements](VERIFIED_MEASUREMENTS.md)
- [Scoped full-100k protocol](../../docs/STANDALONE_100K_ADDENDUM.md)

The qualification figures use 5 timed queries at 10k and 20 at 100k; they must
not be interpreted as a controlled full-query scale comparison. The standalone
100k campaign is not the original four-scale ascending/descending campaign.

## Next steps and stopping rule

Finish and independently verify the second freshly built full 100k round,
preserve both rounds, assemble the final factual handoff, and stop before 250k+
for literature/novelty and protocol review. Operational correctness alone does
not establish research novelty or justify final conclusions.
