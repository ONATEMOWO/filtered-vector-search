# Current verification and handoff — 6 October 2026

## Outcome and boundaries

- Research audit completed before new files were written.
- Sole bounded implementation: offline repetition-sensitivity diagnostic and
  focused tests. No producer/database/schema/configuration changes.
- No new benchmark, database connection, restart, load, graph, or 250k+ execution.
- HEAD remains **38baba3fbf4e84dfb83d0642fe7cc067fcb748f2**.
- No commits, resets, restores or historical-manifest updates were performed.
- New files remain uncommitted for review. One preexisting historical JSON
  formatting modification remains untouched.
- No A5 report PDF, video, screenshots or submission was produced. The supplied
  rubric is covered by the review; actual draft and approved proposal remain absent.

## Files created

Paths are relative to the repository root below; all are new, not replacements.

| File | Purpose |
|---|---|
| analysis/audit_repetition_sensitivity.py | Standard-library-only, input-checksummed offline diagnostic; exclusive output and terminal marker |
| tests/milestone2/test_repetition_sensitivity.py | 20 focused tests: arithmetic, full grid, bad rows, identity, campaign, checksums, overwrite refusal, interrupted output |
| outputs/a5_review_20261006/RESEARCH_AUDIT.md | Research reconstruction, causal progression, claim ledger, control matrix, threats and bounded-work rationale |
| outputs/a5_review_20261006/A5_COVERAGE_AND_OWNERSHIP.md | Actual A5 rubric/feedback coverage, proposal/draft unknowns, report/video evidence, personal ownership questions |
| outputs/a5_review_20261006/FUTURE_PROTOCOL_AND_CONTRIBUTION.md | Hypotheses, correlation models, unaccepted frozen future candidate, contribution levels and literature questions |
| outputs/a5_review_20261006/VERIFICATION.md | This command/result/change record |
| outputs/a5_review_20261006/repetition_diagnostic/diagnostic.json | All30 condition diagnostics, input/generator hashes, query/build identities and worktree provenance |
| outputs/a5_review_20261006/repetition_diagnostic/REPETITION_SENSITIVITY.md | Human-readable, separate-round diagnostic; later-four values explicitly post-hoc sensitivity |
| outputs/a5_review_20261006/repetition_diagnostic/checksums.sha256 | Derived diagnostic payload hashes |
| outputs/a5_review_20261006/repetition_diagnostic/COMPLETE.json | Success marker written last; identifies checksum manifest |
| outputs/a5_review_20261006/REVIEW_CHECKSUMS.sha256 | Final review/code payload hashes, excluding this hash manifest itself |

No tracked file was changed by this review. In particular, the historical
formatting difference existed at the start and still has SHA256
`3707e3624b10d59936c6d53de6d743e71b7346ba83f1359fdf207023d86f3e9b`.
Its original committed bytes remain in Git with SHA256
`492635d51025cf3bb0b063bcf4474971a8f868b5df29d3e39e9d01631055d255`.
Parsed JSON values are equal. The owner's edit was not restored or committed.

## Commands and actual outcomes

Working directory:

```text
/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search
```

Initial read-only state/history checks:

```bash
git status --short
git rev-parse HEAD
git log --oneline --reverse
git diff -- raw_results/milestone_2/20260915T184137Z_bf300f7b1133/failure.json
git ls-files
git remote -v
```

Observed16 commits through38baba3; one preexisting formatting edit. Repository/
parent project searches found no A5 draft or approved proposal; the user later
provided the assignment rubric/deadline, not those missing documents.

Fresh **read-only** full-pair verification, executed successfully:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv-milestone2/bin/python - <<'PY'
from pathlib import Path
import json
from tests.milestone2.verify_run import verify_round_pair
print(json.dumps(verify_round_pair(
    Path('raw_results/milestone_2/20260929T171847Z_f9d4cdb50ba7'),
    Path('raw_results/milestone_2/20260929T172504Z_fa89b474a1c4')
), indent=2, sort_keys=True))
PY
```

Result: passed=true;30,000 stored measured executions,1,000 truth records per
run,15 plans and300 warm-ups per run,20 fresh independent source/NumPy checks
per run; matching source/data/query/truth and distinct physical objects;
actual-restart evidence verified; input hashes unchanged. This revalidates
recorded artifacts and source, not today's live database.

Tests:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-milestone2/bin/python -m unittest tests.milestone2.test_repetition_sensitivity -v
PYTHONDONTWRITEBYTECODE=1 .venv-milestone2/bin/python -m unittest discover -s tests -q
```

Final focused result: **20 tests passed in13.434s**.
Complete suite: **148 tests passed in16.310s**, comprising the earlier128 plus20.
Tests use temporary synthetic fixtures, not new experimental results.
During review, successful derived-output completion was strengthened: a
checksum manifest and final success marker distinguish a complete diagnostic
from preserved partial output. Failure tests confirm incomplete output is
kept without a success marker. No failed real-data diagnostic was generated.

Real-data diagnostic, executed once successfully:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-milestone2/bin/python analysis/audit_repetition_sensitivity.py raw_results/milestone_2/20260929T171847Z_f9d4cdb50ba7 raw_results/milestone_2/20260929T172504Z_fa89b474a1c4 --output outputs/a5_review_20261006/repetition_diagnostic
```

A deliberate second invocation of the identical command exited1 with
`FileExistsError: refusing existing output directory`. Subsequent checksum
checks passed: no output or input was overwritten. To reproduce, choose a
different new directory. Identical computational results are expected for
identical inputs/code; provenance fields can change with repository state.

Static checks, executed successfully:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-milestone2/bin/python - <<'PY'
import ast, subprocess
from pathlib import Path
paths = {Path(p) for p in subprocess.check_output(
    ['git', 'ls-files', '*.py'], text=True).splitlines()}
paths.update([Path('analysis/audit_repetition_sensitivity.py'),
              Path('tests/milestone2/test_repetition_sensitivity.py')])
for p in paths:
    ast.parse(p.read_text(), filename=str(p))
print('PASS AST syntax:', len(paths), 'Python files')
PY
for script in scripts/*.sh; do bash -n "$script" || exit; done
.venv-milestone2/bin/python -m pip check
git diff --check
```

Results:34 Python files parsed; shell syntax passed; no broken requirements;
tracked diff whitespace passed. Pip emitted a cache-directory permission
warning and disabled its cache; this was not a dependency failure.

Independent hash audit used hashlib directly, without the producer checker:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-milestone2/bin/python - <<'PY'
from pathlib import Path
import hashlib, json, subprocess
for d in sorted(Path('raw_results/milestone_2').iterdir()):
    if not d.is_dir():
        continue
    bad = []
    for line in (d / 'checksums.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        if hashlib.sha256((d / name).read_bytes()).hexdigest() != digest:
            bad.append(name)
    print(d.name, 'PASS' if not bad else 'FAIL', bad)
p = 'raw_results/milestone_2/20260915T184137Z_bf300f7b1133/failure.json'
old = subprocess.check_output(['git', 'show', '38baba3:' + p])
new = Path(p).read_bytes()
print('JSON values equal:', json.loads(old) == json.loads(new))
print('committed / working SHA256:',
      hashlib.sha256(old).hexdigest(), hashlib.sha256(new).hexdigest())
PY
```

Result at start and finish: seven manifests PASS; the old Sep15 INVALID run
FAILS only failure.json because of preexisting formatting. Its current bytes
were unchanged by this work. All successful runs remain hash-valid.

Old evidence-bundle check, executed from its directory:

```bash
cd outputs/assignment_evidence
LC_ALL=C shasum -a 256 -c BUNDLE_CHECKSUMS.sha256
```

All15 listed payloads passed before and after new work. Do not interpret that
as “all historical run manifests pass”: the known failure above is separate.

## Independent arithmetic check

A second calculation, without importing the new diagnostic or producer summary
functions, reopened all30k raw records. It used a sorted-middle median, linear
interpolation at(n−1)×0.95, per-query first/later ratios, and exact ID-list
comparison. It matched every per-pass median, paired ratio, first-slower rate,
all-five and later-four median/p95, and identical-result count for all30 rows.
All6,000 query/condition/build cells had identical ordered results across five
repetitions. Input hashes and the terminal marker/payload hashes also passed.

Core independently executed calculation (the outer loop supplied each condition's
dictionary `q` keyed by query ID and repetition):

```python
def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return (xs[(n - 1) // 2] + xs[n // 2]) / 2

all5 = [median([v[i]['duration_ns'] for i in range(1, 6)])
        for v in q.values()]
later = [median([v[i]['duration_ns'] for i in range(2, 6)])
         for v in q.values()]
ratios = [v[1]['duration_ns'] / m for v, m in zip(q.values(), later)]
paired_first_later = median(ratios)
identical = sum(all(v[i]['result_ids'] == v[1]['result_ids']
                    for i in range(2, 6)) for v in q.values())
```

The new diagnostic retains fractional-nanosecond interpolation/medians, including
the final median across200 query medians. The historical producer truncates some
final summary values to integer nanoseconds. All-five medians agreed within
less than1ns; this rounding difference is not altered data or a performance effect.

## Interpretation and unresolved work

Observed example: round1 standard HNSW50% pass medians17.902/1.966/1.621/1.617/
1.572ms; median paired first/later ratio10.877. Not all conditions show a slow
first pass; round1 iterative1% becomes slower in later passes. Report all
conditions and do not infer cache causality or retroactively drop a pass.

Unchanged producer defects/limits: memory-only buffering of partial measurements;
incompletely frozen exact/server settings; no current scale/correlation study;
limited graph replication; fixed-setting/local-host scope. These are next-run
gates or inference boundaries, not claims of wrong completed recall.

Final read-only document audit found no substantive inconsistency or false
completion claim. All71 local Markdown links resolved; new Python/Markdown
files passed trailing-whitespace and EOF checks. Source and old evidence files
were left unchanged from the initial audit state.

Final git status shows only the original tracked failure.json edit plus the
new diagnostic script, test file and review directory as untracked.
The configured remote is https://github.com/ONATEMOWO/filtered-vector-search.git;
no fetch/push/accessibility verification was performed. Review files were not
published, committed, or submitted. Stop for review before further execution.

The final review payload manifest includes both new code files, all four review
documents and the four completed diagnostic files. Verify from repository root:

```bash
LC_ALL=C shasum -a 256 -c outputs/a5_review_20261006/REVIEW_CHECKSUMS.sha256
```

This is a checksum-linked working-tree review, not a new Git commit. Preserve
the manifest with these exact files; changes require a new reviewed snapshot.
