# Full standalone 100k measurements

Descriptive single-scale benchmark observations, not final research conclusions. Both rounds independently verified; 200 measured queries × 5 repetitions per condition, separate physical builds and actual restarts. Latency is the median of per-query medians; recall is the mean of per-query means. Repetitions and rounds are not pooled as independent samples.

| Round | Method | Match rate | Median ms | Canonical Recall@10 | Tie-aware Recall@10 | Returning 10 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | exact | 1% | 2.088 | 1.0000 | 1.0000 | 100.0% |
| 1 | exact | 5% | 4.912 | 1.0000 | 1.0000 | 100.0% |
| 1 | exact | 10% | 7.618 | 1.0000 | 1.0000 | 100.0% |
| 1 | exact | 20% | 13.921 | 1.0000 | 1.0000 | 100.0% |
| 1 | exact | 50% | 26.524 | 1.0000 | 1.0000 | 100.0% |
| 1 | hnsw_iterative | 1% | 15.852 | 0.9835 | 0.9835 | 100.0% |
| 1 | hnsw_iterative | 5% | 4.567 | 0.9660 | 0.9660 | 100.0% |
| 1 | hnsw_iterative | 10% | 3.639 | 0.9565 | 0.9565 | 100.0% |
| 1 | hnsw_iterative | 20% | 2.124 | 0.9515 | 0.9515 | 100.0% |
| 1 | hnsw_iterative | 50% | 1.721 | 0.9635 | 0.9640 | 100.0% |
| 1 | hnsw_standard | 1% | 1.395 | 0.0420 | 0.0420 | 0.0% |
| 1 | hnsw_standard | 5% | 1.754 | 0.2140 | 0.2140 | 0.0% |
| 1 | hnsw_standard | 10% | 1.380 | 0.4130 | 0.4130 | 0.5% |
| 1 | hnsw_standard | 20% | 1.465 | 0.7480 | 0.7480 | 26.0% |
| 1 | hnsw_standard | 50% | 1.901 | 0.9635 | 0.9635 | 99.5% |
| 2 | exact | 1% | 2.440 | 1.0000 | 1.0000 | 100.0% |
| 2 | exact | 5% | 5.716 | 1.0000 | 1.0000 | 100.0% |
| 2 | exact | 10% | 8.555 | 1.0000 | 1.0000 | 100.0% |
| 2 | exact | 20% | 14.578 | 1.0000 | 1.0000 | 100.0% |
| 2 | exact | 50% | 27.623 | 1.0000 | 1.0000 | 100.0% |
| 2 | hnsw_iterative | 1% | 15.581 | 0.9835 | 0.9835 | 100.0% |
| 2 | hnsw_iterative | 5% | 4.416 | 0.9645 | 0.9645 | 100.0% |
| 2 | hnsw_iterative | 10% | 3.219 | 0.9565 | 0.9565 | 100.0% |
| 2 | hnsw_iterative | 20% | 2.063 | 0.9520 | 0.9520 | 100.0% |
| 2 | hnsw_iterative | 50% | 1.351 | 0.9635 | 0.9640 | 100.0% |
| 2 | hnsw_standard | 1% | 1.854 | 0.0420 | 0.0420 | 0.0% |
| 2 | hnsw_standard | 5% | 1.370 | 0.2135 | 0.2135 | 0.0% |
| 2 | hnsw_standard | 10% | 1.352 | 0.4120 | 0.4120 | 0.5% |
| 2 | hnsw_standard | 20% | 1.777 | 0.7490 | 0.7490 | 26.0% |
| 2 | hnsw_standard | 50% | 1.406 | 0.9635 | 0.9635 | 99.5% |

## Recorded phase and resource observations

| Quantity | Round 1 | Round 2 |
|---|---:|---:|
| Exact copy s | 5.969 | 6.457 |
| HNSW table copy s | 3.936 | 2.427 |
| HNSW graph build s | 88.180 | 87.150 |
| Initial ground truth s | 13.966 | 13.507 |
| Ground-truth re-execution s | 13.249 | 13.383 |
| Timed workload plus warm-ups s | 116.356 | 117.213 |
| Operator restart wait s | 32.639 | 61.384 |
| Total before final artifacts s | 290.482 | 317.749 |
| Minimum sampled host available memory bytes | 2,924,490,752 | 2,854,346,752 |
| Minimum sampled free disk bytes | 32,236,519,424 | 32,196,947,968 |
| Client maximum RSS bytes (macOS) | 424,837,120 | 410,820,608 |
| Mechanical full-matrix projection minutes | 95.39 | 94.37 |

Host memory values are phase samples, not continuous peaks or PostgreSQL process memory. Projections are mechanical planning estimates, not bounds. Operator wait is excluded from computational projections. The OS cache was not flushed.

## Source evidence

- [20260929T171847Z_f9d4cdb50ba7](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T171847Z_f9d4cdb50ba7/summary.json) — raw summaries verified against executions.
- [20260929T172504Z_fa89b474a1c4](/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T172504Z_fa89b474a1c4/summary.json) — raw summaries verified against executions.
- [Independent pair proof](FULL_100K_PAIR_VERIFICATION.json) confirms 30,000 executions, identical data/ground truth/source code, distinct rebuilt physical objects and a real restart in each round.
