# Preparation-policy implementation checkpoint - 6 October 2026

This is an implementation checkpoint, **not completion of the empirical
milestone**. At this checkpoint no new database campaign has started. The
question and acceptance diagnostics were frozen before new timing data.

## Starting state and preservation

- Original HEAD: `38baba3fbf4e84dfb83d0642fe7cc067fcb748f2`, branch `main`.
- Prior uncommitted audit: two code/test files and nine review artifacts.
  Reviewed independently, baseline148 tests passed in13.848s, all ten review
  manifest payload hashes passed. Preserved as commit `7dc2f81`.
- Pre-existing user change: formatting-only
  `raw_results/milestone_2/20260915T184137Z_bf300f7b1133/failure.json`.
  It remains uncommitted in the original worktree and was not restored or staged.
- Its working SHA256 remains
  `3707e3624b10d59936c6d53de6d743e71b7346ba83f1359fdf207023d86f3e9b`;
  original committed SHA256 is
  `492635d51025cf3bb0b063bcf4474971a8f868b5df29d3e39e9d01631055d255`.
- `STARTING_STATE.json` records322 starting evidence hashes, all rechecked
  unchanged against the original worktree after implementation.
- New work is on `research/preparation-policy` in sibling worktree
  `filtered-vector-search-preparation`. Ignored symlinks reuse the pinned Python
  environment and local PostgreSQL/dataset runtime, not historical raw outputs.

## Completed work

1. Reconstructed history, SQL, metadata, ground truth, timing, plans, cache
   controls, validators and saved10k/100k evidence. Fresh offline full-pair
   verification passed:30,000 measurements,40 fresh sampled NumPy checks,
   unchanged source/plan/ground-truth evidence. No new PostgreSQL query timings.
2. Selected a matched preparation-policy study before correlation or scale
   expansion. Design and alternatives are in `docs/PREPARATION_POLICY_PROTOCOL.md`.
3. Implemented strict100k-only two-build AB/BA runner reusing audited query/data
   primitives. Each arm uses verified shared-buffer eviction, not restart or
   OS-cache flushing. All five measured passes are retained.
4. Added pass-checkpoint persistence, interruption tests, exact prepared counters,
   before/after session controls, advisory-lock and client-boundary checks.
5. Added an offline verifier and separate analysis implementation, with exact
   schedule/score/provenance checks and source-linked descriptive figures.

New implementation files: `experiments/preparation/{protocol,runner,journal,verify}.py`
and package initializer; `analysis/preparation_policy.py`;
`tests/preparation/{test_protocol,test_runner,test_journal,test_verify,test_analysis}.py`
and package initializer; `config/preparation-policy-v1.json`; the protocol doc;
this checkpoint and starting-state inventory. README's stale qualification-only
opening was corrected. `.gitignore` now ignores either real runtime/environment
directories or worktree symlinks. No historical producer/profile/raw files changed.

## Verification actually run

From the new worktree, except the initial baseline tests in the original:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-milestone2/bin/python -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 .venv-milestone2/bin/python -m experiments.preparation.runner --help
.venv-milestone2/bin/python -m pip check
for script in scripts/*.sh; do bash -n "$script" || exit; done
git diff --check
```

Final complete suite: **213 tests passed in42.497s** (148 prior plus65 new).
An earlier integration pass during implementation passed210 tests in22.450s.
Focused suites:9 protocol,19 runner/journal,20 verifier,17 analysis tests.
Figure tests rendered actual PNGs from **synthetic test fixtures**, not new
database results. AST parsing of all12 new Python files passed; dependency,
shell-syntax and whitespace checks passed. Upstream Matplotlib/pyparsing and
font-cache warnings were nonfatal. Test output describing an INVALID source
checksum is an intentional temporary-fixture failure test, not a real run.

Fresh historical pair-verification command:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python - <<'PY'
from pathlib import Path
import json
from tests.milestone2.verify_run import verify_round_pair
print(json.dumps(verify_round_pair(
    Path('raw_results/milestone_2/20260929T171847Z_f9d4cdb50ba7'),
    Path('raw_results/milestone_2/20260929T172504Z_fa89b474a1c4')
), indent=2))
PY
```

Preservation checks included the review manifest from repository root:
`LC_ALL=C shasum -a 256 -c outputs/a5_review_20261006/REVIEW_CHECKSUMS.sha256`.
An initial invocation from inside the review directory could not resolve its
repository-relative paths; the correctly rooted invocation passed all ten.
That was a command-directory error, not evidence corruption.

## Bugs and open execution boundary

- Cross-review caught a new verifier/legacy-producer shape mismatch:
  `nonfinite_vector_counts` also contains a description. Checking the two counts
  independently preserves the intended invariant; a regression test uses the
  actual committed historical evidence schema.
- A test fixture initially shadowed `unittest.TestCase.run`; its name was fixed.
- Both-arm quality equality alone could conceal equal within-arm changes; the
  analysis support gate now also checks repetition-level quality stability.
- Network access was initially sandbox-blocked. After permission, PostgreSQL
  reported connection refused. `./scripts/postgres_local.sh start` failed with
  `shmat(...): Operation not permitted`; the operator was asked to start the
  project server once from Terminal. No repeated/manual arm restarts are needed.
- The live runner, buffer reset, settings and new artifact verifier have not yet
  been exercised together against PostgreSQL at this checkpoint. Unit/static
  success does not establish empirical validity or a preparation-policy effect.
- The legacy runner's end-of-workload buffering remains historically unchanged;
  incremental persistence applies to the new preparation runner only.

## Next checkpoint

After PostgreSQL is available, launch the fixed campaign from clean committed
source. Verify all raw artifacts before interpreting results, preserve failed
attempts, and produce the factual empirical handoff. Do not label the planned
60,000 observations as completed, edit the A5 PDF, or run250k+.
