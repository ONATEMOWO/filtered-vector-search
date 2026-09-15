CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS milestone2;

DROP TABLE IF EXISTS milestone2.sift_hnsw;
DROP TABLE IF EXISTS milestone2.sift_exact;

CREATE TABLE milestone2.sift_exact (
    id integer PRIMARY KEY CHECK (id >= 0),
    scale_rank integer NOT NULL CHECK (scale_rank >= 0),
    filter_bucket smallint NOT NULL CHECK (filter_bucket BETWEEN 0 AND 99),
    embedding vector(128) NOT NULL
);

CREATE TABLE milestone2.sift_hnsw (
    id integer PRIMARY KEY CHECK (id >= 0),
    scale_rank integer NOT NULL CHECK (scale_rank >= 0),
    filter_bucket smallint NOT NULL CHECK (filter_bucket BETWEEN 0 AND 99),
    embedding vector(128) NOT NULL
);

-- The high target makes the deliberately controlled 100-value bucket
-- distribution visible to the planner. Uniqueness of scale_rank is verified by
-- the harness instead of creating another B-tree on sift_hnsw.
ALTER TABLE milestone2.sift_exact
    ALTER COLUMN filter_bucket SET STATISTICS 1000;
ALTER TABLE milestone2.sift_hnsw
    ALTER COLUMN filter_bucket SET STATISTICS 1000;

COMMENT ON TABLE milestone2.sift_exact IS
    'SIFT benchmark rows for realistic exact filtered search; no vector index.';
COMMENT ON TABLE milestone2.sift_hnsw IS
    'Identical SIFT benchmark rows for forced HNSW search; no filter metadata index.';
COMMENT ON COLUMN milestone2.sift_exact.scale_rank IS
    'Zero-based global rank by SHA256(sift-base-v1|base_id).';
COMMENT ON COLUMN milestone2.sift_exact.filter_bucket IS
    'Controlled metadata: scale_rank modulo 100.';
COMMENT ON COLUMN milestone2.sift_hnsw.scale_rank IS
    'Zero-based global rank by SHA256(sift-base-v1|base_id).';
COMMENT ON COLUMN milestone2.sift_hnsw.filter_bucket IS
    'Controlled metadata: scale_rank modulo 100.';
