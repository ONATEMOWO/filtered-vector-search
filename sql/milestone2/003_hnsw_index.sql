-- No filter_bucket index is created on sift_hnsw: the benchmark runner must
-- route both approximate methods through this vector index.
CREATE INDEX sift_hnsw_embedding_idx
    ON milestone2.sift_hnsw
    USING hnsw (embedding vector_l2_ops)
    WITH (m = 16, ef_construction = 64);
