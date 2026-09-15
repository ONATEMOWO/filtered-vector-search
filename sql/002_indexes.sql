\set ON_ERROR_STOP on

CREATE INDEX smoke_items_embedding_hnsw
    ON smoke_items
    USING hnsw (embedding vector_l2_ops)
    WITH (m = 16, ef_construction = 64);

ANALYZE smoke_items;
ANALYZE smoke_queries;
