-- Exact filtered top-10 for query 1 and the 50% filter.
-- Index scans are disabled only for this transaction so the HNSW index cannot
-- supply approximate neighbors. With no metadata index, this is a sequential
-- scan of the filtered rows followed by an exact top-N sort.
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

-- Standard (non-iterative) HNSW filtered top-10 for the same query/filter.
-- Disabling sequential and bitmap scans makes the chosen approximate access
-- path explicit. The WHERE filter is applied to tuples returned by HNSW.
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
