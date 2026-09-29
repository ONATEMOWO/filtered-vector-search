# Verification and command record

Repository working directory for the commands below:

```text
/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search
```

## Automated and static checks already obtained

The initial resumed suite reproduced two errors in 67 tests because the
preflight lacked `record_resource_projection`. That field was repaired;
subsequent suites passed as regression coverage grew. The consolidated
qualification harness passed 101 tests, the percentile-verifier correction
passed 102, and the full-100k/restart/figure extensions passed **128 tests**.

Commands executed successfully:

```bash
.venv-milestone2/bin/python -m unittest discover -s tests -q
.venv-milestone2/bin/python -m compileall -q experiments tests scripts/acquire_sift1m.py analysis/generate_assignment_figures.py
.venv-milestone2/bin/python -m pip check
git diff --check
for script in scripts/*.sh; do bash -n "$script" || exit; done
.venv-milestone2/bin/python tests/verify_database.py
.venv-milestone2/bin/python tests/verify_results.py
```

The last two checks preserved Milestone 1: live database checks passed and all
250 historical smoke-result rows passed their independent validator. An
additional live Milestone 2 probe audited all 15 prepared generic plans against
the existing 10k database before the corrected harness commit: one vector
parameter, generic-plan counter advancing by one, custom-plan count zero,
correct access path/settings and matching fetched/plan row counts.

The live restart-identity probe read PostgreSQL's postmaster start time,
cluster identifier and all six table/index OIDs/file identifiers; its negative
test correctly rejected the unchanged server. No restart was simulated.

## Executed experiment commands

```bash
.venv-milestone2/bin/python -m experiments.milestone2.runner --config config/milestone2/preflight-10k.json
.venv-milestone2/bin/python -m experiments.milestone2.runner --config config/milestone2/qualification-100k.json
.venv-milestone2/bin/python -m experiments.milestone2.runner --config config/milestone2/qualification-100k.json
.venv-milestone2/bin/python -m experiments.milestone2.runner --config config/milestone2/benchmark-100k-round-1.json
.venv-milestone2/bin/python -m experiments.milestone2.runner --config config/milestone2/benchmark-100k-round-2.json
```

The first 100k qualification invocation failed on loopback permission before
database loading. Its `INVALID.json`, failure traceback and checksums remain
committed. Permission was restored; the second invocation passed. No invalid
attempt was overwritten or merged into successful measurements. Consult
`CURRENT_RESEARCH_STATE.md` for the final status of both full rounds.

The user started PostgreSQL in their own Terminal, then performed each full
round's real restart using:

```bash
./scripts/postgres_local.sh stop && ./scripts/postgres_local.sh start
```

The app sandbox had denied process/shared-memory operations; connecting to an
already running database was allowed after loopback permission was granted.
The full-run harness verifies a later postmaster start time with the same
cluster and unchanged physical objects across the restart. The server is not
restarted during timed measurement.

## Independent verification of preserved runs

These commands passed (read-only, including before/after checksum checks):

```bash
.venv-milestone2/bin/python tests/milestone2/verify_run.py raw_results/milestone_2/20260929T165442Z_3a1810512444
.venv-milestone2/bin/python tests/milestone2/verify_run.py raw_results/milestone_2/20260929T165921Z_bcce4b4163d7
.venv-milestone2/bin/python tests/milestone2/verify_run.py raw_results/milestone_2/20260929T171847Z_f9d4cdb50ba7
```

The final cross-round command executed successfully and re-ran the complete
independent verifier on **both** full rounds (including the second):

```bash
.venv-milestone2/bin/python - <<'PY'
import json
from pathlib import Path
from tests.milestone2.verify_run import verify_round_pair
print(json.dumps(verify_round_pair(
    Path('raw_results/milestone_2/20260929T171847Z_f9d4cdb50ba7'),
    Path('raw_results/milestone_2/20260929T172504Z_fa89b474a1c4')
), indent=2, sort_keys=True))
PY
```

The actual returned JSON is preserved as `FULL_100K_PAIR_VERIFICATION.json`.
Result: `passed=true`, 30,000 timed executions, identical source code/data and
1,000 ground-truth records across rounds, different physical table/index
objects, actual restart verified in each round, and artifact checksums
unchanged. The post-benchmark suite passed 128 tests in 1.406 s; all listed static
and Milestone 1 live/result checks passed again after benchmark completion.

The final packaging check reran the suite: **128 tests passed in 1.745 s**.
All eight preserved Milestone 2 payload checksum manifests passed; no active
run marker remained. Git comparisons confirmed the historical Milestone 1
raw results and three historical Milestone 2 directories were unchanged.
Figure generator, input and output hashes still matched their provenance.
An independent read-only documentation audit matched all 30 full-100k table
rows and resource/plan figures to the saved artifacts; all checked links resolved.
The final staged-file check detected trailing blank lines in three new index
documents; those were removed in a documentation-only follow-up, and the
evidence-bundle checksum file was refreshed. Benchmark artifacts were unchanged.
The all-changes whitespace scan also reports a trailing blank in the preserved
invalid run's `20260929T165840Z_bcce4b4163d7/run.log`. That immutable raw log
was deliberately not edited. The staged documentation check and the complete
source/documentation scan excluding `raw_results` pass:

```bash
git diff --cached --check
git diff 0f5fe34 --check -- . ':(exclude)raw_results'
```

Each verifies the pinned source HDF5 identity and values, deterministic scale
and query selection, full source/table stream linkage, all stored ground-truth
checksums and ties, 20 fresh NumPy ground truths (four per filter), recorded
L2 result distances, every scored recall/completeness/provenance row, exact
schedule coverage, warm-ups, prepared plan linkage, summaries and power/cache
evidence. The qualifier counts are 75/600 timings; round 1 has 15,000.
All runs retain 1,000 ground truths, 1,000 re-executions, 300 warm-ups and 15
plans. Unit tamper tests also reject attempts to finalize already immutable
directories without changing a byte.

## Figure generation

```bash
.venv-milestone2/bin/python -m pip install -r requirements-figures.txt
MPLCONFIGDIR=.runtime/matplotlib .venv-milestone2/bin/python analysis/generate_assignment_figures.py raw_results/milestone_2/20260929T165442Z_3a1810512444 raw_results/milestone_2/20260929T165921Z_bcce4b4163d7 --output-dir outputs/assignment_evidence
```

All three figures were visually inspected. The initial shared latency axis
clipped later-panel bars; the generator was corrected, two regression tests
were added and all three figures regenerated and checked. Rejected derived
files were moved to the parent preservation directory, not deleted. Raw
measurement artifacts were unchanged. The generator refuses existing output
names; use a new directory for a reproduction rather than overwriting evidence.

## Preservation

Before editing, the exact 16 originally modified files were archived alongside
a verified Git history bundle. Locations are under the repository's parent:

```text
outputs/resume-preservation-20260929/uncommitted-files.tgz
SHA256 29f79cde040959b8780f2d9c61159e1bf381f6f54ff1b00f1a07e0702cb42ce2
outputs/resume-preservation-20260929/committed-history.bundle
SHA256 c5d3d30023474d120476d11ad1269c9afa829ca9426d2950779cdd5a37fd1ca3
outputs/resume-preservation-20260929/rejected-figure-render/
```

`git bundle verify` passed. SHA-256 was checked with `LC_ALL=C shasum -a 256`
after the host's unsupported `C.UTF-8` locale caused the unqualified `shasum`
command to fail. This utility failure did not affect experiment data.
