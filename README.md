# Filtered vector search in PostgreSQL/pgvector

This undergraduate research project asks:

> How do filter selectivity and dataset scale affect the recall and query
> latency of standard HNSW and iterative HNSW filtered vector search compared
> with exact filtered search in PostgreSQL/pgvector?

Milestone 1 remains preserved as a verified synthetic smoke pipeline. Milestone
2 adds a separately namespaced SIFT1M benchmark harness for realistic exact,
standard HNSW, and strict-order iterative HNSW search. The currently authorized
Milestone 2 work is limited to a 10,000-row integration preflight and a bounded
100,000-row qualification run; the complete benchmark is deliberately disabled.

## What is included

- PostgreSQL 17 with the real pgvector 0.8.6 extension
- a 20,000-row, 128-dimensional deterministic synthetic smoke dataset
- exact 50%, 20%, 10%, 5%, and 1% metadata filter conditions
- an L2 HNSW index and forced/verified exact and HNSW query paths
- Recall@10, returned-row checks, server-reported latency, raw CSV output, and
  representative JSON `EXPLAIN ANALYZE` plans
- unit and database integration checks

The synthetic vectors are **only for pipeline validation**. A public benchmark
such as SIFT1M should replace them in later research milestones.

## Project layout

```text
analysis/figures/       reserved for later analysis and figures
data/                   deterministic smoke-data generator
data/generated/         generated CSVs (gitignored)
docs/                   method and validity documentation
experiments/            experiment runner and Recall@k implementation
raw_results/            machine-readable outputs and EXPLAIN evidence
scripts/                PostgreSQL bootstrap/control and data-loading scripts
sql/                    schema, indexes, and inspectable query examples
tests/                  unit and live-database verification
compose.yaml            optional pinned pgvector container environment
Makefile                reproducible task entry points
```

## Prerequisites

Verified local path:

- macOS 10.15 or newer
- Python 3.10 or newer (standard library only)
- `curl`, `openssl`, `hdiutil`, and the macOS `codesign` utility
- about 1 GB free disk space

Docker alternative:

- Docker with Compose v2
- Python 3.10 or newer

Docker was not present on the inspected host, so the local Postgres.app path is
the environment actually used for Milestone 1. The Compose definition pins
`pgvector/pgvector:0.8.6-pg17` but is provided as an unverified alternative on
this machine.

## Reproduce with the verified macOS setup

From the repository root:

```bash
make postgres-bootstrap
make postgres-start
make smoke
make postgres-stop
```

The bootstrap downloads the official Postgres.app 2.9.6 PostgreSQL 17 bundle,
checks its SHA-256 digest, and installs it only under gitignored `.runtime/`.
The local cluster listens on `127.0.0.1:55432`, uses trust authentication, and
is intended only for local development. Its Unix socket uses the short path
`/private/tmp/filtered-vector-search-<uid>` to stay below macOS's socket-path
limit even when the repository has a long absolute path.

To rerun individual stages while the server is running:

```bash
make generate
make db-reset
make test
make experiment
```

## Reproduce with Docker Compose

```bash
docker compose up -d
export USE_DOCKER=1
export PGDATABASE=filtered_vector_search
make smoke
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete the
container's database volume.

## Exact and HNSW SQL

The complete runnable examples are in `sql/search_examples.sql`. The exact path
is:

```sql
BEGIN;
SET LOCAL enable_indexscan = off;
SET LOCAL enable_indexonlyscan = off;
SET LOCAL enable_bitmapscan = off;
SELECT id,
       embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1) AS distance
FROM smoke_items
WHERE filter_bucket < 50
ORDER BY embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1), id
LIMIT 10;
ROLLBACK;
```

The standard HNSW path is:

```sql
BEGIN;
SET LOCAL enable_seqscan = off;
SET LOCAL enable_bitmapscan = off;
SET LOCAL hnsw.ef_search = 40;
SET LOCAL hnsw.iterative_scan = 'off';
SELECT id,
       embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1) AS distance
FROM smoke_items
WHERE filter_bucket < 50
ORDER BY embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1)
LIMIT 10;
ROLLBACK;
```

The index is `USING hnsw (embedding vector_l2_ops) WITH (m=16,
ef_construction=64)`. Iterative scanning is explicitly off.

## Outputs

- `raw_results/smoke_results.csv`: one row per measured execution
- `raw_results/smoke_summary.csv`: simple smoke-check aggregation
- `raw_results/filter_counts.csv`: observed filter counts and rates
- `raw_results/environment.json`: versions and run configuration
- `raw_results/explain/*.json`: representative exact and HNSW plans
- `data/generated/generation_metadata.json`: seed, method, and CSV checksums

Latency is PostgreSQL's top-level `Execution Time` from `EXPLAIN ANALYZE`, not a
client wall-clock measurement. See `docs/milestone-1-method.md` for the exact
protocol, Recall@k definition, and validity limitations. `make experiment` also
runs `tests/verify_results.py`, which rejects mislabeled access paths and
recomputes Recall@10 from the recorded IDs.

Smoke output is diagnostic only. It must not be interpreted as evidence about
the research question.

## Milestone 2 qualification

The frozen methodology is `docs/MILESTONE_2_PROTOCOL.md`. Milestone 2 uses the
canonical ANN-Benchmarks SIFT1M HDF5 artifact without normalization, a globally
deterministic SHA-256 scale ranking, exact 50/20/10/5/1 percent metadata
filters, separate exact and HNSW tables, durable exact ground truth, persistent
prepared database connections, and client-side monotonic execute-and-fetch
timing.

The large HDF5 file lives under `.runtime/datasets/`; the generated scale-order
cache lives under ignored `data/generated/milestone2/`. Neither is committed.
Each qualification run creates a new immutable directory
under `raw_results/milestone_2/` with configuration, manifests, ground truth,
raw executions, plans, validation evidence, resource observations, and
checksums.

From the repository root, reproduce the authorized stages with:

```bash
make m2-setup
make m2-acquire
make m2-test
make postgres-start
make m2-preflight
git add raw_results/milestone_2
git commit -m "Record verified 10k SIFT preflight"
make m2-qualification
make postgres-stop
```

`m2-preflight` times 75 executions at 10,000 rows. `m2-qualification`
physically rebuilds at 100,000 rows and times 600 executions. Both stages first
generate exact ground truth for all 200 predetermined queries across all five
filters and independently validate a fixed 20-combination sample. Neither
target can launch 250k, 500k, 1M, or the eventual 120,000-execution matrix.
The runner requires a clean committed worktree at launch, so a finalized
preflight must be verified and committed before starting the 100k stage. It
also records and gates AC-power state.
Milestone 2 uses its own `milestone2` database schema and does not alter the
Milestone 1 tables. The two qualification runs record a documented
`pg_buffercache` reset because the managed qualification host cannot signal the
pre-existing server; the eventual full benchmark continues to require a real
server restart as frozen in the protocol.

All Milestone 2 qualification measurements are infrastructure-validation data,
not research findings or conclusions.
