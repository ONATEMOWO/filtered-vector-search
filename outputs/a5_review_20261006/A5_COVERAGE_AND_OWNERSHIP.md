# A5 coverage and ownership audit — 6 October 2026

This is a technical audit and evidence index, not polished assignment prose,
an A5 report PDF, or a completed video. It distinguishes repository evidence
from student explanations and submission requirements.

## Assignment boundary and missing inputs

The rubric supplied during this review calls for a cumulative **Weeks 1–7**
report PDF with seven sections: overview, completed work, evidence, progress
versus proposal, challenges, current status, and second-half plan. A **3–5
minute video** must demonstrate the actual system. The report must contain the
project/GitHub link. The stated deadline is **Tuesday, 6 October 2026, 14:30**.
The assignment interface's timezone has not been verified; America/Chicago is
the local environment timezone, not proof of the deadline timezone.

The configured Git remote is
[ONATEMOWO/filtered-vector-search](https://github.com/ONATEMOWO/filtered-vector-search).
This was read from local Git configuration; instructor access and remote
publication of today's uncommitted additions have not been verified.

The current A5 draft and approved proposal were not supplied or found in the
repository or its parent project. Therefore this audit cannot certify the
draft's accuracy, compare it line by line with the approved proposal, or
declare the original schedule satisfied. The rubric is now available; the
older A3/A4 documents' statements that no rubric was supplied describe their
earlier preparation, not the present A5 review.

The sibling `filtered-vector-search-a3` is a detached Git worktree at
`0f5fe34`, not an A5 draft. The current audited committed checkpoint is
`38baba3fbf4e84dfb83d0642fe7cc067fcb748f2`. Existing measurements and dated
verification evidence below are from September, not new database experiments
performed for A5 today.

## Seven-section coverage

| Required report section | Evidence available | Coverage and explicit content still needed |
|---|---|---|
| 1. Project overview | [Original/current question](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/MILESTONE_2_PROTOCOL.md:18), [fixed design](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/MILESTONE_2_PROTOCOL.md:26) | Strong question/configuration evidence. Explain the database problem and narrow measured scope; a defensible literature gap is not yet established. |
| 2. Work completed in Weeks 1–7 | [Milestone 1 scope](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/milestone-1-method.md:3), [commit chronology](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/COMMIT_HISTORY.md:8), [full campaign completion](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CURRENT_RESEARCH_STATE.md:24) | Strong cumulative technical evidence. Use actual dates; supply the course calendar before assigning particular commits to academic weeks. Do not count proposed diagnostics as completed. |
| 3. Evidence of progress | [Independent pair proof](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FULL_100K_PAIR_VERIFICATION.json:1), [measurements](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FULL_100K_MEASUREMENTS.md:1), [checks record](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CHECKS_AND_COMMANDS.md:9) | Strong files/results. Include selected readable evidence in the PDF and explain what each proves; do not require the instructor to infer completion from GitHub alone. |
| 4. Progress versus proposal | [Unchanged question](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/MILESTONE_2_PROTOCOL.md:20), [standalone scope addendum](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/STANDALONE_100K_ADDENDUM.md:3) | Partial. Recoverable evolution: synthetic validation to SIFT, realistic exact baseline, iterative HNSW, stronger timing/validation, bounded full 100k. Approved proposal text and original schedule are still needed to identify promised deliverables, deviations, and reasons accurately. |
| 5. Challenges and responses | [Recorded fixes and limitations](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/MILESTONE_2_FACTUAL_HANDOFF.md:253), [preservation record](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CHECKS_AND_COMMANDS.md:145) | Strong concrete history. Explain the prepared-query bug and evidence-preservation issue mechanistically. Also disclose currently open validity and historical-file integrity concerns below. |
| 6. Current status | [Completed/unfinished checkpoint](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CURRENT_RESEARCH_STATE.md:24) | Technically advanced infrastructure and descriptive 100k observations; controlled scale/correlation inference and novelty remain unfinished. Current working-tree state must come from today's handoff, not the September claim that it was clean. |
| 7. Second-half plan | [Existing stop/review gate](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CURRENT_RESEARCH_STATE.md:83), prioritized gates below | A concrete plan is possible. Tie its dates to the real course schedule when supplied; do not invent later deadlines or commit to 250k+ execution before validity review. |

Separate submission checks remain necessary: create and inspect the actual PDF,
record and watch the actual 3–5 minute video, insert a verified accessible
project/GitHub URL in the PDF, and verify submission. None is established by
the existence of this Markdown audit. Local absolute file links in this audit
are navigation aids on this machine, not a substitute for an accessible
submitted report and repository URL.

## Dated progress, not an invented seven-week log

| Recorded date | Commits / milestone | What it establishes |
|---|---|---|
| 15 September 2026 | `cd199a2` | Real PostgreSQL/pgvector synthetic smoke pipeline: 20k item vectors, exact versus standard HNSW, saved plans and validation. |
| 15 September 2026 | `61519cd`, `8682a76`, `8f537a4`, `0f5fe34` | Initial SIFT qualification harness, preserved version-gate failure and correction, stronger ground truth/query summaries, historical corrected 10k run. Later superseded for measurement use, not erased. |
| 29 September 2026 | `97eb5b0`, `6708bfa`, `8f62bb3` | Reconciled strict profile, single-vector/actual prepared-plan verification and immutability fixes; verified corrected 10k run; bounded p95 verifier tolerance correction. |
| 29 September 2026 | `5549ad1`, `1b68328` | Preserved permission-blocked attempt, then successful physically loaded 100k qualification. |
| 29 September 2026 | `5d6a16f`, `3692827` | Explicit standalone-100k/restart scope and source-linked qualification figures. |
| 29 September 2026 | `e7952e5`, `f671005` | Two separately rebuilt full 100k rounds and independent pair proof. |
| 29 September 2026 | `fa5a03f`, `38baba3` | Evidence packaging and final documentation/checksum follow-up; no larger-scale run. |
| 6 October 2026 | This review, uncommitted additions | Completed research/assignment audit and checksum-linked offline repetition-sensitivity diagnostic of the existing full100k data; 20 focused tests and 148 full-suite tests passed. No new database benchmark. Week7 attribution still follows the course cutoff, not an invented weekly history. |

Git author and committer timestamps establish these repository dates. They do
not establish time spent, academic-week attribution, conceptual ownership, or
which tasks were promised by a missing proposal. The earlier handoff records
128 passing tests and independent run verification; those are **previously
obtained September checks**, not a claim that this audit has rerun them today.
Any current tests/diagnostics must be reported with their actual command,
result, and scope in the current handoff.

Current Oct6 evidence is in [verification record](VERIFICATION.md) and the
[completed offline diagnostic](repetition_diagnostic/REPETITION_SENSITIVITY.md).
Fresh read-only pair verification passed both full runs. The observed
repetition dependence is a limitation of existing timing interpretation,
not a newly measured database result or a proven cache failure.

## Scope and method statements the report must get right

The formal question remains about selectivity and dataset scale. The completed
full experiment is narrower: one fixed 100k SIFT subset on one host, L2,
`k=10`, synthetic controlled metadata, three specified access paths, 200 fixed
queries, five repetitions per condition, and two HNSW builds. It does not yet
isolate the effect of scale or metadata/vector correlation.

| Possible draft statement | Required factual correction / qualification |
|---|---|
| “The SIFT1M benchmark is complete.” | The pinned source contains one million base vectors; full measurement is at **100,000** rows. The larger-scale campaign remains unexecuted. |
| “We tested 30,000 independent queries.” | There are 200 unique measured query vectors, 15 method/filter conditions, five repetitions, and two builds: 30,000 executions, not independent samples. |
| “The 10k and 100k results prove the scaling effect.” | Preflight, qualification and full runs differ in query counts, repetitions and cache boundaries. Do not treat their figures as matched scale evidence. |
| “Metadata is random and realistic.” | `filter_bucket = scale_rank mod 100` is deterministic synthetic metadata after hash ordering. It controls selectivity but does not demonstrate realistic semantics or empirical independence from geometry. |
| “A PostgreSQL restart clears all caches.” | Full runs verified a real server restart; the OS page cache was not flushed. Qualification used a separately documented shared-buffer eviction procedure. |
| “Latency is PostgreSQL execution time.” | That describes Milestone 1's separate instrumented `EXPLAIN ANALYZE` execution. Milestone 2 measures client execute-and-fetch latency of the same prepared query whose results are scored. |
| “Exact search is deliberately forced to scan every row.” | That describes the smoke baseline. Milestone 2 exact search has a metadata B-tree, no vector index and enabled normal planner paths; it may use bitmap/parallel/sequential plans. |
| “Iterative HNSW guarantees the exact answer.” | Full-100k observations show complete result counts for iterative HNSW, but mean recall below one. Completeness and exact-neighbor recovery are distinct. |
| “Passing tests proves the scientific conclusions.” | Tests and validators support implementation/artifact correctness under their checks. They do not remove confounding, establish novelty or justify broad inference. |
| “All results are immutable and the tree is clean.” | Harness finalization, checksums and Git make alteration detectable; they are not write-once storage. A historical failure artifact is currently reformatted in the worktree. |
| “The project is on schedule.” | Infrastructure is substantially complete; the promised schedule and proposal are unavailable. State completed and open tasks, and qualify schedule judgments. |

These are corrections to check for, not quotations from an unavailable A5
draft. A line-by-line correction pass requires that draft.

README scope also needs careful interpretation: its
[opening qualification-only status](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/README.md:9)
is stale relative to its
[later standalone-100k authorization](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/README.md:160).
The early “what is included” and SQL/timing sections primarily describe
Milestone 1. Use the current-state file, full-100k addendum and stage-specific
artifacts for the midterm's current scope, rather than quoting the opening
README as an up-to-date completion statement.

## Instructor-feedback closure

| Feedback | Closed or substantially addressed | Still unresolved / why the suggested fix alone is insufficient |
|---|---|---|
| Specify dataset sizes | [Protocol](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/MILESTONE_2_PROTOCOL.md:28) declares 100k/250k/500k/1M; completed physical 10k/100k stages are identified separately. | Explicit sizes are not evidence of a matched multi-scale experiment. Only full 100k exists. |
| Specify k and index settings | `k=10`; `m=16`, `ef_construction=64`, `ef_search=40`; standard off and strict-order iterative mode with declared limits. [Method/settings evidence](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/MILESTONE_2_FACTUAL_HANDOFF.md:103) | Fixed settings bound the claim. They do not establish that the selected budget is optimal or representative of all HNSW configurations. |
| Clarify cache and warm-up | [Protocol](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/MILESTONE_2_PROTOCOL.md:337) and [restart addendum](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/STANDALONE_100K_ADDENDUM.md:28) define restart versus qualification fallback, 20 disjoint warm-ups per block, no OS flush. | A stated policy is not proof of thermal isolation, stable cache convergence or absence of time/order effects. Existing-data sensitivity diagnostics can expose limitations, not retrospectively fix the run. |
| Address metadata/vector correlation; compare random and cluster-correlated metadata | [Synthetic metadata semantics](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/MILESTONE_2_PROTOCOL.md:123) are reproducible and exact-selectivity. | Correlation is untested. Cluster alignment alone can change query/filter difficulty or selectivity; a future explicit condition must hold counts fixed and quantify local enrichment/association. Do not add a “clustered” label without measurement or reinterpret legacy buckets. |

The instructor's feedback is useful design pressure, not a complete research
agenda. Resolving a configuration omission is different from establishing a
mechanism, external validity or a novel contribution.

## Challenges: resolved mechanisms versus open risks

| Challenge | Recorded response / present status |
|---|---|
| Vendor-labelled PostgreSQL version string falsely rejected | `8682a76` preserved the failed run and checked parsed/raw/numeric version identity appropriately. |
| Strict preflight profile mismatch | `97eb5b0` added the missing `record_resource_projection` profile field; stricter configuration checks could then proceed. |
| HNSW vector binding and prepared-plan ambiguity | Single bound vector plus distance alias; actual generic prepared statement audited. Student should explain why auditing a separate custom plan would not prove the timed statement's route. |
| Unsafe re-finalization of completed evidence | Finalizers check active state before mutation; regression coverage checks byte preservation. This does not prevent manual/editor changes outside the harness. |
| Independent p95 differed by 1 ns | `6708bfa` permits only that narrow percentile roundoff tolerance; data were not changed to force agreement. |
| Loopback/restart permissions | Failed qualification preserved separately; successful new attempt followed. Full rounds required real operator-performed restarts, verified by the harness. |
| Initial qualification figure clipped later bars | Generator corrected, regression checks added, rejected derived rendering preserved; raw benchmark data unchanged. |
| Current historical `failure.json` reformatted | Open integrity exception: displayed JSON values are unchanged, bytes/checksum are not. Preserve and disclose; do not rewrite the historical checksum or silently restore the user's edit. |
| Scale, correlation, statistical inference and novelty | Open research work. More executions alone would not resolve these validity gaps. |

## Priority gates for the second half

1. **Close the midterm evidence boundary.** Supply the actual proposal/draft,
   confirm deadline timezone and week mapping, disclose the dirty artifact,
   and finish the required PDF/video with qualified claims. Verify the
   repository URL and access. Preserve all existing raw data.
2. **Audit uncertainty before new compute.** The bounded offline repetition-
   sensitivity diagnostic is now completed and independently checked.
   Keep it separate from benchmark artifacts. Its
   outputs can diagnose repeat/order sensitivity; they are not new graph
   builds or proof of an adequate warm-up policy.
3. **Select a narrow contribution after literature review.** Distinguish
   documented post-filtering behavior from a potential contribution in
   controlled selectivity/scale/correlation characterization. Do not claim a
   routing algorithm or novel decision surface before the evidence supports
   it. Record unanswered literature questions and limitations.
4. **Freeze a comparable protocol.** Decide whether a new baseline campaign
   is required. Hold query set, filters, correlation mode, settings,
   repetition policy, restart/warm-up, timing and validation constant across
   physically rebuilt scales. Keep exploratory old runs out of the new
   confirmatory estimate. Predeclare the query/build aggregation and target
   claims rather than pooling repeated timings as independent samples.
5. **Validate correlation before benchmarking it.** Introduce explicit new
   modes only, keep historical rank-mod100 semantics, hold selectivity fixed,
   and quantify achieved association/local enrichment. A small preflight
   should establish that the manipulation changes what it claims to change.
6. **Authorize bounded scale execution only after those gates.** Recheck
   resource feasibility, preserve failures, retain per-build/per-query raw
   evidence, and analyze uncertainty before making scale/crossover claims.
   Execution at 250k+ is not part of this A5 review.

These are ordered research gates, not promised dates; the missing course
calendar and proposal are needed for a credible calendar schedule.

## Best report evidence and a 3–5 minute video path

No screenshots, PDF or video were created by this audit. Existing files can
be shown directly. Do not trigger a new benchmark merely to film it.

| Approximate video time | Existing evidence | Demonstration and caveat |
|---|---|---|
| 0:00–0:35 | [Current scope and results](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CURRENT_RESEARCH_STATE.md:24) | State the question, completed 100k scope, and the still-open scale/correlation questions. |
| 0:35–1:20 | [Actual SQL](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/sql/milestone2/search_examples.sql), [schema](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/sql/milestone2/001_schema.sql) | Explain real PostgreSQL tables, vector(128), filter and three search paths. Code walkthrough is not evidence of a new execution today. |
| 1:20–2:15 | [Full-round plan assertions](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T172504Z_fa89b474a1c4/plan_assertions.jsonl), [pair proof](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FULL_100K_PAIR_VERIFICATION.json:1) | Show actual executed PostgreSQL paths, 30k recorded executions, equal data/truth, distinct physical graphs and real restart proof. This demonstrates the recorded system; if a live demonstration is required, explicitly distinguish any newly authorized read-only check from historical execution. |
| 2:15–3:10 | [Full 100k table](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FULL_100K_MEASUREMENTS.md:3) | Explain one restrictive-filter example and completeness versus recall. Keep rounds separate; use “observed here,” not a universal conclusion. |
| 3:10–4:00 | [Challenge record](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/MILESTONE_2_FACTUAL_HANDOFF.md:253), [checks record](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CHECKS_AND_COMMANDS.md:79) | Explain one real bug and how the check would catch it; acknowledge that correctness tests are not scientific inference. |
| 4:00–5:00 if needed | [Completed timing diagnostic](repetition_diagnostic/REPETITION_SENSITIVITY.md), [verification record](VERIFICATION.md), this audit's next gates | Show one repeat-dependent example and explain why no cache cause is established; state what remains untested. This is offline analysis of recorded executions, not a fresh database benchmark. |

For the PDF, a compact completed/partial/open table plus a selected raw-plan
excerpt and the per-round descriptive measurement table provide stronger
evidence than many unannotated screenshots. The existing
[qualification recall figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_recall_at_10.png),
[completeness figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_result_completeness.png)
and
[latency figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_client_latency.png)
are optional **qualification** illustrations, not full-100k or matched-scale
findings; their 10k/100k panels use different query counts.

For an actual short program demonstration without a new database experiment,
run the diagnostic's three arithmetic tests while recording, then show the
checksum-linked real-data diagnostic and a saved full-round PostgreSQL plan:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-milestone2/bin/python -m unittest tests.milestone2.test_repetition_sensitivity.FormulaTests -v
```

Those are synthetic validation tests, not newly obtained database measurements.
Explain that distinction aloud; a screen of saved plans is historical execution
evidence, not a claim that PostgreSQL was queried live in the video.

## Questions the student must be able to answer personally

1. What is the formal research question, what narrower question has actually
   been measured, and what would falsify the proposed mechanism?
2. Why cannot the existing 10k/100k measurements isolate a scale effect?
3. How is a SIFT row chosen, what does `filter_bucket < 1` mean, and why do
   the five qualifying sets nest? Which role is played by a fixed hash domain
   versus the earlier synthetic random seed?
4. Why is the exact baseline on a separate table with a metadata B-tree? What
   planner comparison does that allow, and what production-routing claim does
   it prevent?
5. Why can standard HNSW return fewer than ten rows even when 1,000 rows
   qualify? What does iterative scanning change, and what are its limits?
6. Why are supplied unfiltered SIFT neighbors not valid ground truth for
   reduced scales or filtered queries?
7. How are boundary ties handled, and how do canonical recall, tie-aware
   recall, and completeness differ?
8. What exactly is inside the latency interval? Why is `EXPLAIN ANALYZE`
   outside it, and why must the audited prepared statement match the timed one?
9. What did the single-vector SQL correction fix? Can you explain the
   before/after plan risk rather than merely name the changed function?
10. Which caches survive a PostgreSQL restart? What does the fixed warm-up
    demonstrate, and what does it fail to establish?
11. What is the inferential unit: timing repetition, query, or rebuilt graph?
    Why are 30,000 timings not 30,000 independent observations?
12. How would you hold selectivity constant while varying metadata/vector
    correlation, and how would you verify that correlation changed?
13. What guarantee is provided by checksums and terminal run markers? Why
    does harmless-looking JSON reformatting still create an integrity issue?
14. Which observations are facts, which interpretations are hypotheses, and
    which claims would require additional datasets, machines or builds?
15. Which design/code/debugging steps used assistant or other tool support?
    What did you personally inspect, reproduce or independently verify? Can
    you explain and modify the core query, recall calculation and validation
    logic without treating generated code or passing tests as ownership proof?

The presence of code, a Git author field, or this audit cannot answer those
ownership questions on the student's behalf.
