# Pre-experiment implementation checkpoint — 6 October 2026

Starting HEAD: `d3bcae685e2f61679e7dc1b7b230264480dffce1`.
Work proceeds in the separate `research/metadata-association` worktree.
`STARTING_STATE.json` records 858 historical evidence-file hashes, including
the untouched working bytes of the original worktree's unrelated old
`20260915T184137Z_bf300f7b1133/failure.json` formatting edit.

The chosen milestone is the matched metadata-association/physical-scale
campaign frozen in `docs/METADATA_ASSOCIATION_PROTOCOL.md` and
`config/metadata-association-v1.json`. Historical experiment source, profiles,
raw runs, preparation study, analysis bundles and A5 PDF were not changed.
No empirical association run had started when this checkpoint was written.

## Checks already completed

- Historical baseline: 213 tests passed in 57.950 seconds.
- Complete current suite: **311 tests passed in 63.981 seconds**:
  `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m unittest discover -s tests -p 'test_*.py' -q`.
- 61 Python files passed AST parsing without bytecode writes.
- `.venv-milestone2/bin/python -m pip check`: no broken requirements.
- `bash -n scripts/postgres_local.sh scripts/bootstrap_postgres_macos.sh scripts/load_smoke_data.sh scripts/clean_results.sh`: passed.
- `git diff --check`: passed; staged additions are checked again before commit.
- Live readiness: PostgreSQL17.11, pgvector0.8.6, shared_buffers128MB,
  max_worker_processes8, block_size8192, no other PostgreSQL clients, AC power.
  Host snapshot: 17,179,869,184 bytes total RAM, 5,564,399,616 available,
  34,265,411,584 disk bytes free. Readiness is not a resource-use measurement.

The suite's printed INVALID lines are intentional mocked failure tests, not
empirical runs. Nonfatal Matplotlib/pyparsing deprecation and font-cache
warnings occurred; figure generation tests passed. The first readiness attempt
was blocked by the app's network sandbox; the user granted network access and
the same local database check then passed. No server restart was needed.

## Defects found and corrected before data collection

Aligned producer/verifier contracts for the metadata algorithm name,
`gate_passed`, six client-boundary checks including load, and inherited
100k-prefix hashes. Added a producer assertion requiring all three persistent
method connections. The new mode-specific prepared-statement collector must
match association SQL (the historical collector intentionally selects another
schema). Hardened source-helper identity, physical schema/relations,
predecessor continuity and numerical truth checks. Regression tests exercise
missing methods, changed source, malformed metadata, plans, recall, resources,
interruption preservation and invalid terminal evidence.

One analysis test initially compared `/var` against its resolved macOS
`/private/var` alias; the fixture assertion now compares resolved paths.
These were implementation/test corrections before any new outcome was seen,
not protocol retuning after an inconvenient research result.

## Execution gate

Commit the reviewed implementation and start from a clean worktree. First:

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.association.runner --scale 100000 --build 1
```

For each returned run directory, run the independent offline verifier:

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m experiments.association.verify RUN_DIRECTORY
```

Preserve and commit evidence before the next stage; then use the runner with
`--scale 250000 --build 1`, `--scale 250000 --build 2`, and
`--scale 100000 --build 2` in order, each with `--previous PREVIOUS_RUN_DIRECTORY`.
Every transition verifies its predecessor and identical implementation bytes.
Do not execute analysis/tests concurrently with timed database work. Stop on a
failed manipulation/correctness/resource gate, preserve evidence, and do not
retune the anchor or silently relax checks. No 500k/1M run belongs to this milestone.

After completed database stages only:

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m analysis.metadata_association RUN1 RUN2 RUN3 RUN4 --output NEW_ANALYSIS_DIRECTORY
```

The analyzer also accepts an ordered partial prefix, explicitly labeled partial;
it reruns offline verification and checks all input hashes before/after.
