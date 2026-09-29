# Evidence to show in a 2–5 minute progress video

These are existing files, not claimed screenshots. The PNGs are generated
qualification figures, not final research graphs. Do not present their unequal
5-query/20-query panels as a controlled scale comparison.

1. **0:00–0:40 — question, scope and completion.** Open
   [current research state](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CURRENT_RESEARCH_STATE.md).
   Explain that exact, standard HNSW and iterative HNSW are verified on real
   PostgreSQL/pgvector; two full 100k builds are complete and larger scales are paused.
2. **0:40–1:30 — show the evidence, not only the claim.** Open
   [independent pair verification](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FULL_100K_PAIR_VERIFICATION.json).
   Show `passed`, 30,000 timings, identical data/truth and different physical objects.
   Open [tests and commands](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CHECKS_AND_COMMANDS.md) for the 128-test result.
3. **1:30–2:40 — actual execution and descriptive measurements.** Open
   [full 100k table](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FULL_100K_MEASUREMENTS.md), retaining separate rounds.
   For plan evidence, show the restrictive-filter
   [exact plan](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165921Z_bcce4b4163d7/plans/0ffd6dd701bee50ad9bd.json),
   [standard HNSW plan](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165921Z_bcce4b4163d7/plans/52a7ff640bced76a38ed.json) and
   [iterative plan](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165921Z_bcce4b4163d7/plans/3a3ec4e5e54cff721a5d.json).
   Label these three plans as **bounded 100k qualification**, not full-round timing.
4. **2:40–4:00 — visual validation and limitations.** Optional
   [qualification recall figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_recall_at_10.png),
   [completeness figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_result_completeness.png) and
   [latency figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_client_latency.png).
   Explain that returning ten is not the same as recovering the exact neighbors,
   and that validation measurements are not final findings.
5. **4:00–5:00 — challenges and next checkpoint.** Use
   [factual handoff](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/MILESTONE_2_FACTUAL_HANDOFF.md) for the profile,
   prepared-query and evidence-preservation fixes. End with literature/novelty
   and protocol review before 250k+, not a scaling conclusion.

For assignment-specific extracts:
[A3](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/A3_FACTUAL_EVIDENCE.md) and
[A4](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/A4_FACTUAL_EVIDENCE.md).
For provenance:
[commit history](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/COMMIT_HISTORY.md) and
[exact changed-file inventory](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/FILE_INVENTORY.md).

