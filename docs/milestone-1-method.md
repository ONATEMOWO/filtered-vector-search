# Milestone 1 method and validity notes

## Scope

This milestone validates a small end-to-end pipeline using PostgreSQL and the
real pgvector extension. It does not test dataset scale, use SIFT1M, enable
iterative HNSW, perform statistical analysis, or support research conclusions.

## Smoke dataset

`data/generate_smoke_data.py` creates 20,000 independent 128-dimensional
synthetic item vectors and five independent query vectors. Components are drawn
from `Uniform[-1,1]`, each vector is L2-normalized, and values are written with
eight decimal places. Python's `random.Random` (MT19937) is seeded with
`20260915`.

The item metadata contains one of 100 integer buckets. A balanced list of
buckets is shuffled using the same deterministic random stream. Therefore,
`filter_bucket < N` matches exactly `N%` of the default 20,000-row dataset for
`N` in 1 through 100. The smoke run exercises thresholds 50, 20, 10, 5, and 1.

This construction validates control of selectivity and plumbing only. Uniform
random vectors and independent metadata are not representative of real vector
neighborhoods or metadata correlations.

## Search paths

Both paths use Euclidean distance (`<->`) and `k=10`.

- Exact disables ordinary, index-only, and bitmap index scans within its
  transaction, preventing HNSW use. It sequentially filters the table, sorts
  all qualifying distances, and uses `id` only as a deterministic tie-breaker.
- Standard HNSW disables sequential and bitmap scans within its transaction so
  plan selection is explicit. It fixes `hnsw.ef_search=40` and
  `hnsw.iterative_scan=off`.

The HNSW index uses `vector_l2_ops`, `m=16`, and `ef_construction=64`. Filtering
is post-filtering on tuples visited by standard HNSW. A restrictive filter can
therefore return fewer than `k` rows; that outcome is recorded rather than
silently padded.

For each query/filter/method combination, one unrecorded warm-up is followed by
five recorded executions. Result IDs come from the query execution. Latency is
the top-level `Execution Time` in milliseconds reported by a separate
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` execution of the same query and
session-local settings. It excludes `psql` startup/network time but includes
executor time and `EXPLAIN ANALYZE` instrumentation overhead.

Recall@k is:

`|approximate_top_k IDs intersect exact_top_k IDs| / |exact_top_k IDs|`

All current filters have at least `k` qualifying rows, so the denominator is 10.
Missing HNSW rows reduce recall. Ordering inside the returned top-k set does not
affect recall.

## Validity limitations

- The 20,000-row dataset is deliberately small and synthetic.
- One machine, one PostgreSQL instance, five queries, and five repetitions are
  insufficient for performance conclusions.
- Cache state is only lightly controlled by a single warm-up; the database is
  not restarted between conditions.
- Exact and HNSW results are run separately from their timed `EXPLAIN ANALYZE`
  executions.
- Planner settings force the intended access paths. This verifies algorithms,
  but it does not measure PostgreSQL's unconstrained plan choice.
- `EXPLAIN ANALYZE` adds instrumentation overhead.
- Metadata is independent of vector values; real filtered-vector datasets can
  have strong correlations.
- The local verified run uses macOS and a project-local Postgres.app build.
  Container behavior may differ and was not executable on the inspected host.
- The server's Unix socket is placed under `/private/tmp` because macOS limits
  socket paths to 103 bytes; database files remain under `.runtime/`.
