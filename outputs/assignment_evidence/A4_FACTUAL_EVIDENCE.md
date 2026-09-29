# A4 factual evidence — measured progress and limitations

This document provides verified progress evidence without assuming an A4 rubric. No assignment rubric was supplied. The following numbers come only from the completed corrected 10k preflight and bounded 100k qualification on 29 September 2026. See [CURRENT_RESEARCH_STATE.md](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/CURRENT_RESEARCH_STATE.md) for subsequent full-100k campaign status.

## Completed work and preliminary measurements

The 100k qualification physically loaded **100,000 vectors into each of two tables** and built a new HNSW graph. It covered three methods, five exact selectivities, 20 timed queries, and two repetitions: **600 measured executions**. It passed 1,000 exact-ground-truth re-executions, 20 independent NumPy checks, 15 plan audits, and all recorded row/completeness checks, with zero execution errors. The corrected 10k run passed its 75-execution preflight.

Selected 100k qualification measurements:

| Method | Match rate | Median latency (ms) | Mean Recall@10 | Returning 10 |
|---|---:|---:|---:|---:|
| Exact | 50% | 38.483 | 1.000 | 100% |
| Standard HNSW | 50% | 1.902 | 0.955 | 100% |
| Iterative HNSW | 50% | 14.504 | 0.955 | 100% |
| Exact | 1% | 2.035 | 1.000 | 100% |
| Standard HNSW | 1% | 1.388 | 0.045 | 0% |
| Iterative HNSW | 1% | 26.936 | 0.995 | 100% |

Latency is client-observed execute-and-fetch time, reduced to a median per query before the condition median. Recall is query-averaged; completeness is execution-based. These are small qualification samples. Unusual condition timings, including iterative HNSW at 50%, are preserved rather than explained away or selectively removed.

At 100k, exact-table copy took **6.240 s**, HNSW-table copy **2.624 s**, graph construction **99.187 s**, initial ground truth **15.291 s**, and its deterministic re-execution **16.375 s**. Total runtime before final artifacts was **172.135 s**. The graph occupied **83,132,416 bytes**; recorded table/index relation bytes totaled **206,438,400**. Phase snapshots are observations, not continuous peak-memory measurements.

## Challenges and preserved evidence

- An independent p95 recomputation differed by one nanosecond because equivalent interpolation formulas round differently. Commit `6708bfa` permits only a 1 ns p95 tolerance; other summary fields still require equality.
- A 100k attempt failed before database loading because loopback connection permission was denied. Its invalid artifacts remain committed as `5549ad1`; the successful rerun is a separate immutable directory committed as `1b68328`.
- Qualification used documented shared-buffer eviction because of host process restrictions. Full benchmark rounds require a real verified PostgreSQL restart and cannot silently inherit that substitute.

## Reproduction and video evidence

The [README](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/README.md) supplies setup commands. Existing results can be checked with `.venv-milestone2/bin/python tests/milestone2/verify_run.py` followed by the chosen run directory. Each verifier is read-only.

- [Complete qualification measurement table](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/VERIFIED_MEASUREMENTS.md)
- [Completeness figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_result_completeness.png) and [latency figure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/outputs/assignment_evidence/qualification_client_latency.png)
- [100k phase timings](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165921Z_bcce4b4163d7/phase_metrics.json) and [resource observations/projection](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165921Z_bcce4b4163d7/resource_observations.json)
- [Preserved permission failure](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165840Z_bcce4b4163d7/failure.json)

A short video can show the completed validation report, one completeness figure, one real plan, and the current-state checkpoint. The files above are screen-recording material; no screenshots are claimed.

## Unfinished work and next steps

The qualification-based projection estimates roughly **113 minutes** for the eventual multi-scale pipeline and **2.06 GB** of 1M table/index relation bytes. It assumes linear phase/storage scaling and unchanged observed query latency; it is not a bound or a measured larger-scale result. The full 100k campaign is documented separately. Stop before 250k+ for literature/novelty review, evaluate the protocol and resource budget, then obtain review before larger-scale work. Synthetic metadata, one machine, cache effects, small qualification query sets, and fixed HNSW parameters limit interpretation. No statistical inference or final research conclusions are claimed.
