# A3 factual evidence — implementation and verification

This is a factual progress-report source, not a claim that an unspecified A3 rubric has been satisfied. No assignment rubric was supplied. It describes verified qualification work completed on 29 September 2026. Subsequent campaign status is recorded in [CURRENT_RESEARCH_STATE.md](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CURRENT_RESEARCH_STATE.md).

## Research question and completed implementation

The project asks how filter selectivity and dataset scale affect recall and query latency for standard and iterative HNSW relative to exact filtered search in PostgreSQL/pgvector.

The working pipeline uses PostgreSQL **17.11**, pgvector **0.8.6**, SIFT1M vectors with **128 dimensions**, Euclidean distance, and **k=10**. The canonical SIFT file is checksum-pinned. Global SHA-256 ordering selects nested scales reproducibly; `filter_bucket = scale_rank % 100` creates exact 50%, 20%, 10%, 5%, and 1% match rates. Metadata remains synthetic. Separate physical tables give exact search a metadata B-tree and HNSW its own freshly built vector index.

All methods bind the query vector once. Persistent prepared connections time the same execute-and-fetch operation whose results are scored. Saved plans audit the actual generic prepared statements. Durable exact ground truth includes boundary ties; missing approximate results reduce recall through the fixed denominator of ten.

## Verified qualification evidence

| Check | Corrected 10k preflight | Physical 100k qualification |
|---|---:|---:|
| Timed query vectors × repetitions | 5 × 1 | 20 × 2 |
| Timed executions across 15 method/filter conditions | 75 | 600 |
| Disjoint-query warm-up executions | 300 | 300 |
| Exact ground-truth combinations and deterministic re-executions | 1,000 each | 1,000 each |
| Independent NumPy ground-truth checks | 20 | 20 |
| Prepared-statement plan audits | 15 | 15 |
| Execution errors / failed plan audits | 0 / 0 | 0 / 0 |

The full automated suite subsequently passed **128 tests** before the standalone-100k extension was committed as `5d6a16f`. Qualification artifacts were independently checked against source vectors, plans, recall calculations, scheduling, summaries, and checksums. Milestone 1 evidence was preserved.

## Challenges and corrections

- Strict preflight validation required `record_resource_projection`; the missing profile field was reconciled.
- HNSW originally bound the vector twice. A single parameter plus `ORDER BY distance` preserves index ordering. Plan capture was further corrected to explain the workload's prepared generic statement.
- Re-finalizing an immutable run could remove its checksum manifest. Finalizers now check the active-write state before any mutation; regression tests verify byte-for-byte preservation.

## Files to show in a 2–5 minute video

1. [Protocol and method SQL](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/docs/MILESTONE_2_PROTOCOL.md): introduce the question and fixed design.
2. [10k validation report](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165442Z_3a1810512444/validation_report.json): show concrete completed checks.
3. [100k plan assertions](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165921Z_bcce4b4163d7/plan_assertions.jsonl): demonstrate real PostgreSQL access paths.
4. [Recall figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_recall_at_10.png): explain validation behavior and its limits.

These are existing files suitable for screen recording; no screenshots are claimed. The saved [figure provenance](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/figure_provenance.json) links the figures to their source hashes.

## Unfinished work and conclusions

Qualification measurements validate the infrastructure; they are not final findings. A full 100k campaign has separate status in the current-state file. Literature/novelty review, 250k+ execution, statistical analysis, and final research conclusions remain unfinished. No final research conclusions are claimed.
