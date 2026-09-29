# Milestone 2 benchmark protocol

## Status and change control

This document freezes the accepted Milestone 2 design for the filtered-vector
search study. It is the methodological source of truth for the implementation.
The implementation must not silently change any choice below. A necessary
change must be documented, given a new protocol/configuration identity, and
reported before results from differing protocols are combined.

Milestone 2 implements and qualifies the benchmark infrastructure. It does not
authorize the complete benchmark matrix or support research conclusions.

## Fixed research scope

The research question remains:

> How do filter selectivity and dataset scale affect the recall and query
> latency of standard HNSW and iterative HNSW filtered vector search compared
> with exact filtered search in PostgreSQL/pgvector?

The fixed design is:

| Item | Value |
|---|---|
| PostgreSQL | 17.11 |
| pgvector | 0.8.6 |
| Dataset | SIFT1M in the ANN-Benchmarks HDF5 representation |
| Base vectors | 1,000,000 |
| Query vectors | 10,000 |
| Supplied neighbors | 100 per query |
| Vector dimension | 128 |
| Stored vector type | `vector(128)` (single-precision components) |
| Distance | Euclidean/L2 using `<->` and `vector_l2_ops` |
| Top-k | 10 |
| Final scales | 100,000; 250,000; 500,000; 1,000,000 |
| Filter selectivities | 50%, 20%, 10%, 5%, 1% |
| Methods | realistic exact; standard HNSW; strict-order iterative HNSW |
| Concurrency | one active query at a time |
| Final measured queries | 200 |
| Final warm-up queries | 20, disjoint from measured queries |
| Final repetitions | five per query/condition/round |
| Final rounds | two, with a newly built HNSW index in each round |

The eventual complete matrix contains:

```text
4 scales x 5 filters x 3 methods x 200 queries x 5 repetitions x 2 rounds
= 120,000 timed executions
```

That complete matrix is deliberately disabled during this qualification stage.

## SIFT1M acquisition and validation

The canonical artifact is:

```text
https://ann-benchmarks.com/sift-128-euclidean.hdf5
```

The dataset file is kept outside Git at
`.runtime/datasets/sift-128-euclidean.hdf5`. A static, version-controlled source
manifest records the canonical URL and expected identity. A generated runtime
or run-level acquisition record contains the UTC download time, response
metadata, observed byte size and SHA-256, HDF5 keys, shapes, dtypes, attributes,
and all validation outcomes. Reruns must not mutate the static source manifest,
and must reject a file whose digest differs from the pinned expected digest.

The pinned canonical artifact identity is:

```text
byte size = 525128288
SHA-256  = dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984
```

Required validation gates are:

- base vectors (`train` in the ANN-Benchmarks file): `1,000,000 x 128`;
- query vectors (`test`): `10,000 x 128`;
- supplied neighbor IDs (`neighbors`): `10,000 x 100`;
- base/query vectors and supplied distances have little-endian float32 dtype;
- neighbor IDs have little-endian int32 dtype and fall in `0..999999`;
- all base and query components are finite;
- no required array, row, or vector is missing.

The canonical file's only required root attribute is `distance=euclidean`.

ANN-Benchmarks calls the index/base array `train`; it must not be confused with
the separate learning-vector file in the original SIFT distribution. HNSW does
not require training, so only the base vectors, query vectors, and supplied
neighbors are required here.

The supplied vector values must not be normalized or rounded. SIFT IDs remain
zero-based so the supplied neighbor IDs can be compared directly. The loader
must use round-trip-safe float32 serialization into pgvector.

## Deterministic scale and metadata construction

Every one of the one million base IDs receives a global deterministic sort key:

```text
SHA256(UTF8("sift-base-v1|" + decimal_base_id))
```

Rows are sorted by `(digest, base_id)`. `scale_rank` is the zero-based position
in this global ordering. The base rows at scale `N` are exactly those with
`scale_rank < N`. The resulting rank/ID manifest is checksummed and reused; it
must not be recomputed from an already truncated input.

The canonical one-million-ID order is pinned independently of its cache
container. Its little-endian int32 payload SHA-256 is
`5fff299d2950d88779871ffa4b21660c51d295c44f09ffbee82bac7f164b1fc9`.
With the pinned NumPy runtime, the `.npy` cache SHA-256 is
`73913a6dc24c281c58e222bcd1f277fdd45ff48faa37bf511bad1a842490184e`.
The loader verifies both digests, dtype, shape, complete `0..999999` range,
and permutation uniqueness before selecting any physical scale.

Controlled metadata is:

```text
filter_bucket = scale_rank mod 100
```

Queries use literal predicates:

```sql
filter_bucket < 50
filter_bucket < 20
filter_bucket < 10
filter_bucket < 5
filter_bucket < 1
```

Because every planned and qualification scale is divisible by 100, expected
counts are exact:

| Scale | 50% | 20% | 10% | 5% | 1% |
|---:|---:|---:|---:|---:|---:|
| 10,000 preflight | 5,000 | 2,000 | 1,000 | 500 | 100 |
| 100,000 | 50,000 | 20,000 | 10,000 | 5,000 | 1,000 |
| 250,000 | 125,000 | 50,000 | 25,000 | 12,500 | 2,500 |
| 500,000 | 250,000 | 100,000 | 50,000 | 25,000 | 5,000 |
| 1,000,000 | 500,000 | 200,000 | 100,000 | 50,000 | 10,000 |

Each scale is physically loaded and receives a newly constructed HNSW index.
A predicate over a larger HNSW graph must never be used to simulate scale.

This metadata is synthetic and deliberately independent of vector content. It
controls selectivity but does not model semantic or correlated metadata.

## Deterministic query selection

All 10,000 query IDs receive this key:

```text
SHA256(UTF8("sift-query-v1|" + decimal_query_id))
```

They are sorted by `(digest, query_id)`. The first 200 are the eventual measured
query set; the next 20 are the disjoint warm-up set. The selected IDs, order,
vector digests, and selection-manifest digest are preserved. Qualification runs
use declared prefixes of the 200-query measured set but still generate ground
truth for all 200 selected queries at each loaded scale.

## Physical database design

Every scale uses two ordinary logged tables in schema `milestone2`, populated
with identical records in identical insertion order:

- `milestone2.sift_exact` contains the primary key, global scale rank, controlled filter
  bucket, and vector. It has a B-tree on `filter_bucket` and no vector index.
- `milestone2.sift_hnsw` contains the same columns and rows. It has its primary-key B-tree
  and the HNSW vector index, but no B-tree on `filter_bucket`.

`scale_rank` is not declared unique, because that would create an unnecessary
additional B-tree on the HNSW table; uniqueness is verified explicitly.

After loading and index construction, the harness must:

1. verify equal row counts and identical IDs, ranks, buckets, and vectors;
2. verify dimensions and the absence of null/non-finite data;
3. set the `filter_bucket` statistics target to 1,000;
4. run `VACUUM (ANALYZE, FREEZE)` on both tables;
5. preserve `pg_stats`, index definitions, exact filter counts, relation sizes,
   and index sizes;
6. make no data or statistics changes during measured execution.

The exact table's metadata index is part of the realistic exact baseline. Its
planner may legitimately choose a sequential, B-tree, bitmap, or parallel plan.
The HNSW table omits that metadata index so a selective B-tree cannot replace
the requested HNSW access path.

## Exact ground truth

Ground truth is computed on `milestone2.sift_exact` before any measured executions and is
stored as a durable checksummed artifact. For every loaded scale, filter, and
all 200 predetermined measured queries, execute exact L2 search with all vector
index paths structurally unavailable:

```sql
SELECT id,
       embedding <-> $1::vector AS distance
FROM milestone2.sift_exact
WHERE filter_bucket < <literal-threshold>
ORDER BY distance
FETCH FIRST 10 ROWS WITH TIES;
```

For each combination preserve:

- canonical top-10 IDs and full-precision distances;
- every ID tied at the tenth-neighbor distance;
- IDs strictly closer than the tenth-neighbor distance;
- boundary distance;
- qualifying-row count;
- scale, threshold, and query ID;
- generation SQL/method and artifact checksum.

Canonical top ten is defined by sorting `(distance, id)` and taking ten. Exact
ground truth must return at least ten qualifying rows for every condition.

Validation includes deterministic re-execution and an independent array-based
brute-force check for a fixed stratified sample of at least 20 combinations per
loaded scale. At the eventual one-million-row unfiltered scale, all 200 measured
queries will additionally be checked against SIFT's supplied top-100 IDs with
boundary-tie awareness. Supplied full-scale, unfiltered neighbors must never be
used as filtered or reduced-scale ground truth.

## Search methods

All methods bind the query vector directly as a prepared `vector` parameter.
There is one prepared statement per literal filter threshold, so exact planner
selectivity is not hidden behind a filter parameter.
`plan_cache_mode=force_generic_plan` is fixed for all method connections; the
only bound value is the query vector, which does not alter the declared filter
selectivity. Statement preparation occurs during the pre-warm-up plan audit,
outside timing, and the same statements are reused during warm-up and timing.

### Realistic exact filtered search

```sql
SELECT id,
       embedding <-> $1::vector AS distance
FROM milestone2.sift_exact
WHERE filter_bucket < <literal-threshold>
ORDER BY distance, id
LIMIT 10;
```

No scan-path GUC is disabled on the exact connection. Since
`milestone2.sift_exact` has no
vector index, all valid plans produce exact distances and ranking.

### Standard filtered HNSW

```sql
SELECT id,
       embedding <-> $1::vector AS distance
FROM milestone2.sift_hnsw
WHERE filter_bucket < <literal-threshold>
ORDER BY distance
LIMIT 10;
```

Using the output alias keeps a single server parameter and PostgreSQL expands
the alias to the indexed distance expression during planning. Qualification
rejects the run unless the resulting plan uses the required HNSW index order.

Settings on its dedicated connection are:

```sql
SET hnsw.ef_search = 40;
SET hnsw.iterative_scan = 'off';
SET work_mem = '64MB';
SET enable_seqscan = off;
SET enable_bitmapscan = off;
```

### Strict-order iterative filtered HNSW

The SQL is identical to standard HNSW. Settings are:

```sql
SET hnsw.ef_search = 40;
SET hnsw.iterative_scan = 'strict_order';
SET hnsw.max_scan_tuples = 20000;
SET hnsw.scan_mem_multiplier = 1;
SET work_mem = '64MB';
SET enable_seqscan = off;
SET enable_bitmapscan = off;
```

The HNSW index is constructed with:

```text
operator class = vector_l2_ops
m = 16
ef_construction = 64
maintenance_work_mem = 1GB
max_parallel_maintenance_workers = 0
```

The last two settings make qualification build conditions explicit and are
captured from the build session; they do not change the HNSW graph parameters.

There is no HNSW parameter sweep. JIT is disabled consistently for all three
method connections. A 120-second statement timeout is applied and any timeout
is recorded as a failed execution, never discarded. Prepared statements use
`plan_cache_mode=force_generic_plan`; because every filter threshold is a
literal and only the query vector is bound, this does not hide filter
selectivity from the exact planner.

## Run order and repetition policy

The unit of scheduling is a `(method, filter)` block. Block order is derived by
sorting on a stored SHA-256 schedule key containing protocol identity, stage,
round, scale, method, and filter. Within a block:

1. execute each of the 20 disjoint warm-up queries once without recording it as
   a measured execution;
2. execute the declared number of repetition rounds;
3. in every repetition, deterministically hash-shuffle the measured query IDs;
4. never run all repetitions for one query consecutively;
5. keep one query active at a time.

The final experiment has two complete rounds. Round A runs scales ascending and
round B runs them descending. The HNSW index is rebuilt for every scale/round.
Repetitions characterize timing noise and are not independent query samples;
latency is first reduced across repetitions for each query and only then
summarized across query vectors.

## Warm-up and cache policy

Milestone 2 measures a controlled operationally warmed workload. It makes no
claim of a perfectly warm or perfectly cold cache.

For each scale/round, loading, index creation, vacuum/analyze, and checkpointing
finish before measurement. PostgreSQL is then restarted to reset shared
buffers. The macOS filesystem cache is not flushed. Every method/filter block
executes its fixed 20-query warm-up before measurement. Plan-gate executions
occur before this warm-up so their cache effects are subsumed by the declared
warm-up.

For the two qualification runs only, the managed host cannot signal the
pre-existing verified PostgreSQL process and cannot allocate a second server's
shared-memory segment. After `CHECKPOINT`, the qualification harness therefore
snapshots `pg_buffercache`, calls `pg_buffercache_evict(bufferid)` for every
observed buffer, records successful and unsuccessful evictions plus before/after
cache summaries, and then performs the complete fixed warm-up. This is an
explicit qualification-only implementation substitution. The eventual full
benchmark still requires the accepted PostgreSQL restart boundary and may not
silently inherit this fallback.

No unrelated workload runs during measurement. The machine is connected to AC
power and its macOS energy mode is fixed and recorded. Cold-cache testing is out
of scope for this milestone.

## Latency measurement

Milestone 2 uses the exact-pinned PostgreSQL Python driver with persistent
connections. Connection creation, session configuration, statement
preparation, vector selection, and warm-up occur outside the timed interval.

For every measured execution, `time.perf_counter_ns()` surrounds the same
prepared-statement execution and complete fetch whose IDs are scored:

```text
start_ns -> execute -> fetch all rows -> end_ns
latency_ns = end_ns - start_ns
```

Raw integer nanoseconds are preserved. This is prepared-query, client-observed,
execute-and-fetch latency over the same local transport for all methods. It
does not include connection establishment or statement preparation.

`EXPLAIN ANALYZE` execution time is not benchmark latency.

## Plan and setting verification

Before each measured method/filter block, the harness runs this outside the
timed workload:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    TIMING OFF,
    SUMMARY ON,
    FORMAT JSON
)
...
```

The same connection also records explicit `current_setting(...)` values for
every relevant GUC.

The audit uses `EXPLAIN ... EXECUTE` on the actual driver-prepared generic
statement, not a separately planned copy of its SQL. Each artifact records
the prepared statement's SQL, one-vector parameter type, and generic/custom
plan counters before and after EXPLAIN. The generic counter must advance by
one and the custom counter must remain zero.

For exact search, validation proves that `milestone2.sift_exact` has no vector index and
preserves whichever exact plan PostgreSQL naturally chooses. For both HNSW
methods it verifies:

- an HNSW `Index Scan` using `sift_hnsw_embedding_idx`;
- vector-distance ordering on the index scan;
- the metadata predicate attached as post-filtering to that scan;
- root and scan actual-row evidence consistent with the fetched result;
- `ef_search = 40`;
- the expected iterative mode;
- iterative tuple/memory limits where applicable.

A routing or settings failure invalidates and stops that qualification run; it
must never be recorded as a valid measurement.

## Recall, completeness, and row validation

For every timed execution retain ordered result IDs and distances, returned
count, `returned_k`, shortfall, canonical Recall@10, tie-aware Recall@10,
filter-validity result, and distance-order result.

Canonical recall is:

```text
|approximate IDs intersect canonical exact top-10 IDs| / 10
```

For tie-aware recall, let `C` be exact IDs strictly closer than the tenth
distance and `T` be all exact IDs tied at that distance:

```text
(|approximate intersect C| + min(10 - |C|, |approximate intersect T|)) / 10
```

The fixed denominator means missing approximate results reduce recall.
Completeness is reported separately as the fraction of executions returning
exactly ten qualifying rows. Every returned ID must belong to the loaded scale,
satisfy the filter, be unique, and appear in nondecreasing distance order.
Invalid returned rows fail the run rather than merely lowering recall.

## Append-only reproducibility artifacts

Every execution creates a new exclusive directory:

```text
raw_results/milestone_2/<run_id>/
```

The run ID contains a safe UTC timestamp and a configuration digest. An
existing directory is never reused. A run directory is writable only while it
has an `ACTIVE` marker; successful finalization writes validation and checksums,
removes `ACTIVE`, and writes `COMPLETE`. A completed directory is immutable to
the harness.

Each run must preserve:

- immutable resolved configuration and its digest;
- Git commit and dirty-state flag;
- dataset acquisition manifest and checksum;
- environment, hardware, power, and runtime manifest;
- PostgreSQL `SHOW ALL` plus method-specific settings;
- scale, query-selection, filter, and run-order manifests;
- durable ground truth and its checksum;
- one machine-readable row per timed execution;
- plan JSON and explicit setting evidence;
- table statistics and relation/index sizes;
- data-load, index-build, ground-truth, validation, and total durations;
- validation report, errors/timeouts, and stdout/stderr log;
- disk/RAM observations and projected full-run resources;
- a final SHA-256 manifest for generated artifacts.

Artifact writes occur outside query timing. Execution rows may be buffered per
block and flushed at block boundaries. The checksum file excludes itself.
Configuration changes produce a new configuration digest and run identity.

## Qualification stages authorized now

Only the following two stages may be executed before review.

### Stage A: 10,000-row integration preflight

- Physically load the globally selected first 10,000 rows into both tables.
- Build a new 10,000-row HNSW index.
- Generate ground truth for all 200 predetermined measured queries and all five
  filters.
- Independently validate at least 20 stratified combinations.
- Time the first five predetermined measured queries, one repetition each, for
  all methods and filters: 75 measured executions.
- Use all 20 predetermined warm-up queries.
- Exercise every loading, routing, timing, recall, completeness, artifact, and
  checksum path.

These measurements validate infrastructure only.

### Stage B: 100,000-row qualification

- Drop/recreate and physically load the globally selected first 100,000 rows.
- Build a new 100,000-row HNSW index.
- Generate ground truth for all 200 predetermined measured queries and all five
  filters.
- Independently validate at least 20 stratified combinations.
- Time the first 20 predetermined measured queries, two repetitions each, for
  all methods and filters: 600 measured executions.
- Use all 20 predetermined warm-up queries.
- Record exact load/build/ground-truth/runtime durations, artifact size,
  relation sizes, disk/RAM pressure, observed latency range, and a projected
  resource budget for the eventual complete matrix.

The query/repetition counts above resolve the accepted protocol's deliberately
bounded qualification subset; they are not the final sample size.

## Stop condition

After successful Stage A and Stage B execution, stop for review. Do not
automatically run the complete 100,000-row workload, 250,000, 500,000, or
1,000,000 scales. Do not add parameter sweeps, relaxed-order HNSW, other
algorithms or datasets, concurrency tests, statistical inference, final plots,
or research conclusions.

## Interpretation limitations

- Qualification measurements are infrastructure evidence, not research
  findings.
- Controlled filters are synthetic and independent of SIFT geometry.
- Results ultimately apply to SIFT1M, L2, `k=10`, and the fixed HNSW settings.
- One local machine and single-client execution limit external validity.
- Exact is allowed to use its realistic metadata B-tree, while HNSW is forced
  to the requested vector index; this studies the named access methods rather
  than unconstrained PostgreSQL method selection.
- Operationally warmed results do not characterize cold-cache behavior.
- Two final HNSW builds reveal limited build-to-build variation but do not fully
  characterize graph-construction randomness.
- Index-build time and query latency answer different questions and must remain
  separate.
