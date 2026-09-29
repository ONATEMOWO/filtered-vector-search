# Verified qualification measurements

Infrastructure-validation results only; these are not final research findings.
Latency is client-observed prepared-query execute-and-fetch time, reduced to a
median per query before taking the condition median. Recall is averaged per
query before the condition mean. Repetitions are not independent query samples.
Completeness is the fraction of executions returning exactly 10 qualifying rows.
The filter metadata is synthetic and independent of SIFT vector content.

| Scale | Method | Match rate | Queries | Repetitions | Median ms | Canonical Recall@10 | Tie-aware Recall@10 | Returning 10 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | Exact | 1% | 5 | 1 | 0.746 | 1.000 | 1.000 | 100.0% |
| 10,000 | Exact | 5% | 5 | 1 | 0.476 | 1.000 | 1.000 | 100.0% |
| 10,000 | Exact | 10% | 5 | 1 | 0.563 | 1.000 | 1.000 | 100.0% |
| 10,000 | Exact | 20% | 5 | 1 | 2.094 | 1.000 | 1.000 | 100.0% |
| 10,000 | Exact | 50% | 5 | 1 | 2.848 | 1.000 | 1.000 | 100.0% |
| 10,000 | Standard HNSW | 1% | 5 | 1 | 0.711 | 0.000 | 0.000 | 0.0% |
| 10,000 | Standard HNSW | 5% | 5 | 1 | 1.435 | 0.160 | 0.160 | 0.0% |
| 10,000 | Standard HNSW | 10% | 5 | 1 | 1.217 | 0.380 | 0.380 | 0.0% |
| 10,000 | Standard HNSW | 20% | 5 | 1 | 0.666 | 0.820 | 0.820 | 20.0% |
| 10,000 | Standard HNSW | 50% | 5 | 1 | 0.660 | 1.000 | 1.000 | 100.0% |
| 10,000 | Iterative HNSW (strict order) | 1% | 5 | 1 | 6.185 | 1.000 | 1.000 | 100.0% |
| 10,000 | Iterative HNSW (strict order) | 5% | 5 | 1 | 2.099 | 1.000 | 1.000 | 100.0% |
| 10,000 | Iterative HNSW (strict order) | 10% | 5 | 1 | 1.476 | 1.000 | 1.000 | 100.0% |
| 10,000 | Iterative HNSW (strict order) | 20% | 5 | 1 | 0.997 | 1.000 | 1.000 | 100.0% |
| 10,000 | Iterative HNSW (strict order) | 50% | 5 | 1 | 0.980 | 1.000 | 1.000 | 100.0% |
| 100,000 | Exact | 1% | 20 | 2 | 2.035 | 1.000 | 1.000 | 100.0% |
| 100,000 | Exact | 5% | 20 | 2 | 5.649 | 1.000 | 1.000 | 100.0% |
| 100,000 | Exact | 10% | 20 | 2 | 11.663 | 1.000 | 1.000 | 100.0% |
| 100,000 | Exact | 20% | 20 | 2 | 28.258 | 1.000 | 1.000 | 100.0% |
| 100,000 | Exact | 50% | 20 | 2 | 38.483 | 1.000 | 1.000 | 100.0% |
| 100,000 | Standard HNSW | 1% | 20 | 2 | 1.388 | 0.045 | 0.045 | 0.0% |
| 100,000 | Standard HNSW | 5% | 20 | 2 | 1.471 | 0.270 | 0.270 | 0.0% |
| 100,000 | Standard HNSW | 10% | 20 | 2 | 1.625 | 0.485 | 0.485 | 0.0% |
| 100,000 | Standard HNSW | 20% | 20 | 2 | 6.112 | 0.815 | 0.815 | 40.0% |
| 100,000 | Standard HNSW | 50% | 20 | 2 | 1.902 | 0.955 | 0.955 | 100.0% |
| 100,000 | Iterative HNSW (strict order) | 1% | 20 | 2 | 26.936 | 0.995 | 0.995 | 100.0% |
| 100,000 | Iterative HNSW (strict order) | 5% | 20 | 2 | 3.725 | 0.965 | 0.965 | 100.0% |
| 100,000 | Iterative HNSW (strict order) | 10% | 20 | 2 | 3.077 | 0.955 | 0.955 | 100.0% |
| 100,000 | Iterative HNSW (strict order) | 20% | 20 | 2 | 2.667 | 0.950 | 0.950 | 100.0% |
| 100,000 | Iterative HNSW (strict order) | 50% | 20 | 2 | 14.504 | 0.955 | 0.955 | 100.0% |

Source runs (all payload checksums verified before plotting):

- `20260929T165442Z_3a1810512444` — `/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165442Z_3a1810512444`
- `20260929T165921Z_bcce4b4163d7` — `/Users/temz/Documents/Codex/2026-09-15/i-am-beginning-an-undergraduate-database/filtered-vector-search/raw_results/milestone_2/20260929T165921Z_bcce4b4163d7`

The figures are descriptive grouped bars, with no smoothing, significance
tests, or claims about larger scales. The panels use different qualification
query/repetition counts where specified and must not be interpreted as a
controlled full-scale comparison.
