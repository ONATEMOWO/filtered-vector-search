-- Milestone 2 query templates. The runner prepares one statement per literal
-- threshold (50, 20, 10, 5, and 1) and binds only the query vector. Threshold
-- 50 is shown here as the representative runnable preparation.

DEALLOCATE ALL;
SET SESSION jit = off;
SET SESSION statement_timeout = '120s';
SET SESSION plan_cache_mode = force_generic_plan;

-- Durable exact ground truth, including every ID tied at the kth boundary.
PREPARE m2_ground_truth_filter_50 (vector) AS
SELECT id,
       embedding <-> $1 AS distance
FROM milestone2.sift_exact
WHERE filter_bucket < 50
ORDER BY distance
FETCH FIRST 10 ROWS WITH TIES;

-- Realistic exact search. Do not disable any scan paths on this connection.
PREPARE m2_exact_filter_50 (vector) AS
SELECT id,
       embedding <-> $1 AS distance
FROM milestone2.sift_exact
WHERE filter_bucket < 50
ORDER BY distance, id
LIMIT 10;

-- Standard filtered HNSW settings for its dedicated persistent connection.
SET SESSION jit = off;
SET SESSION statement_timeout = '120s';
SET SESSION work_mem = '64MB';
SET SESSION enable_seqscan = off;
SET SESSION enable_bitmapscan = off;
SET SESSION hnsw.ef_search = 40;
SET SESSION hnsw.iterative_scan = 'off';
PREPARE m2_hnsw_standard_filter_50 (vector) AS
SELECT id,
       embedding <-> $1 AS distance
FROM milestone2.sift_hnsw
WHERE filter_bucket < 50
ORDER BY distance
LIMIT 10;

-- Strict-order iterative HNSW settings for a separate persistent connection.
SET SESSION jit = off;
SET SESSION statement_timeout = '120s';
SET SESSION work_mem = '64MB';
SET SESSION enable_seqscan = off;
SET SESSION enable_bitmapscan = off;
SET SESSION hnsw.ef_search = 40;
SET SESSION hnsw.iterative_scan = 'strict_order';
SET SESSION hnsw.max_scan_tuples = 20000;
SET SESSION hnsw.scan_mem_multiplier = 1;
PREPARE m2_hnsw_iterative_strict_filter_50 (vector) AS
SELECT id,
       embedding <-> $1 AS distance
FROM milestone2.sift_hnsw
WHERE filter_bucket < 50
ORDER BY distance
LIMIT 10;

-- Plan evidence is collected outside benchmark timing. Supply an actual vector
-- value to EXECUTE in the harness.
--
-- EXPLAIN (
--     ANALYZE,
--     BUFFERS,
--     SETTINGS,
--     TIMING OFF,
--     SUMMARY ON,
--     FORMAT JSON
-- ) EXECUTE m2_hnsw_standard_filter_50(<vector-literal>);
