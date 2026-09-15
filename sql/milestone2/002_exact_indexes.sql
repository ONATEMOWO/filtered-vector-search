-- This metadata B-tree is intentionally present only on the exact table.
-- PostgreSQL remains free to choose it, a bitmap path, a sequential scan, or a
-- parallel exact plan according to filter selectivity and collected statistics.
CREATE INDEX sift_exact_filter_bucket_idx
    ON milestone2.sift_exact (filter_bucket);
