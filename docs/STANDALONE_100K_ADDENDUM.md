# Scoped full-100k authorization — 29 September 2026

The user's resumed instruction permits a full 100k benchmark only after the
corrected 10k preflight and bounded 100k qualification pass, if local resources
permit. Both qualification stages passed independent verification. Their
immutable evidence is recorded in `8f62bb3` and `1b68328`, respectively.

This addendum authorizes only `standalone-100k-v1`. The original protocol JSON,
qualification configurations, research question, data, methods and settings
remain unchanged. The complete four-scale experiment is still disabled.

## Precisely bounded workload

Two independently invoked stages, `benchmark-100k-round-1` and
`benchmark-100k-round-2`, each physically recreate the two 100,000-row tables
and build a fresh HNSW index. Each stage has 200 measured queries, five
repetitions, three methods and five filters: 15,000 measured executions.
Each also has all 1,000 exact ground truths, all 1,000 deterministic
re-executions, 20 independently validated combinations, 300 warm-ups and
15 actual prepared-generic-plan audits. The two rounds total 30,000 timings.
No validation requirement is reduced from qualification.

One invocation is one physical round. The explicit experiment round number
is retained in schedules and build identities. Run directories, checksums and
summaries stay separate; a pair verifier must confirm identical selected data
and ground truth but newly created physical table/index identities.

## Actual restart, not the qualification fallback

After each load/build/ground-truth phase, the runner closes preparation and
waits for the operator to restart the local PostgreSQL server. It records a
new postmaster start time, the same cluster identity and unchanged physical
table/index identities across that restart. It then opens new persistent
method sessions, performs plan audits, and applies the normal per-block
warm-up. No OS-cache flush is claimed. Buffer eviction cannot substitute for
this restart. Human restart-wait time is recorded separately and excluded
from projected computational cost. The operator must not change data or
configuration during the wait.

## Interpretation and stopping rule

These are standalone 100k rounds, not the original multi-scale campaign's
ascending-scale Round A and descending-scale Round B. Later larger scales
must not be silently appended to this campaign and represented as that design.
Repetitions remain repeated observations, not independent query samples;
round summaries retain build identity. No final research conclusion follows
from qualification or this single-scale campaign alone.

Before any 250k, 500k or 1M execution, stop for literature/novelty review and
an explicit protocol checkpoint. Configurations reject those scales.

## Reproduction

Start on AC power with a clean committed worktree and the pinned dataset.
Run each command from the repository root; substitute actual output directory
names in verification/commit commands. Do not run the two stages concurrently.

```bash
.venv-milestone2/bin/python -m experiments.milestone2.runner --config config/milestone2/benchmark-100k-round-1.json
# When the runner reports it is waiting, in a second terminal:
./scripts/postgres_local.sh stop && ./scripts/postgres_local.sh start
# After completion, independently verify RUN_1 and commit its artifacts:
.venv-milestone2/bin/python tests/milestone2/verify_run.py raw_results/milestone_2/RUN_1
git add raw_results/milestone_2/RUN_1
git commit -m "Record verified standalone full 100k round 1"
.venv-milestone2/bin/python -m experiments.milestone2.runner --config config/milestone2/benchmark-100k-round-2.json
# At the second runner's restart boundary, in a second terminal:
./scripts/postgres_local.sh stop && ./scripts/postgres_local.sh start
.venv-milestone2/bin/python tests/milestone2/verify_run.py raw_results/milestone_2/RUN_2
```

Verify the pair and preserve the second run before drawing even descriptive
across-round comparisons. Larger-scale execution remains unauthorized.
