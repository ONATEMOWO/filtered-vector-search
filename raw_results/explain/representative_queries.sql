-- exact, query_id=1, filter_bucket < 50
SET LOCAL enable_indexscan = off;
SET LOCAL enable_indexonlyscan = off;
SET LOCAL enable_bitmapscan = off;
SET LOCAL enable_seqscan = on;
SET LOCAL jit = off;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id,
       embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1) AS distance
FROM smoke_items
WHERE filter_bucket < 50
ORDER BY embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1), id
LIMIT 10;

-- exact, query_id=1, filter_bucket < 1
SET LOCAL enable_indexscan = off;
SET LOCAL enable_indexonlyscan = off;
SET LOCAL enable_bitmapscan = off;
SET LOCAL enable_seqscan = on;
SET LOCAL jit = off;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id,
       embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1) AS distance
FROM smoke_items
WHERE filter_bucket < 1
ORDER BY embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1), id
LIMIT 10;

-- hnsw, query_id=1, filter_bucket < 50
SET LOCAL enable_seqscan = off;
SET LOCAL enable_bitmapscan = off;
SET LOCAL hnsw.ef_search = 40;
SET LOCAL hnsw.iterative_scan = 'off';
SET LOCAL jit = off;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id,
       embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1) AS distance
FROM smoke_items
WHERE filter_bucket < 50
ORDER BY embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1)
LIMIT 10;

-- hnsw, query_id=1, filter_bucket < 1
SET LOCAL enable_seqscan = off;
SET LOCAL enable_bitmapscan = off;
SET LOCAL hnsw.ef_search = 40;
SET LOCAL hnsw.iterative_scan = 'off';
SET LOCAL jit = off;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id,
       embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1) AS distance
FROM smoke_items
WHERE filter_bucket < 1
ORDER BY embedding <-> (SELECT embedding FROM smoke_queries WHERE query_id = 1)
LIMIT 10;
