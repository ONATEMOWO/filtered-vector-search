\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS smoke_queries;
DROP TABLE IF EXISTS smoke_items;

CREATE TABLE smoke_items (
    id bigint PRIMARY KEY,
    filter_bucket smallint NOT NULL CHECK (filter_bucket BETWEEN 0 AND 99),
    source_label text NOT NULL CHECK (source_label = 'smoke-synthetic'),
    embedding vector(128) NOT NULL
);

CREATE TABLE smoke_queries (
    query_id integer PRIMARY KEY,
    embedding vector(128) NOT NULL
);

COMMENT ON TABLE smoke_items IS
    'Deterministic synthetic smoke-test data for pipeline validation; not research data.';
COMMENT ON COLUMN smoke_items.filter_bucket IS
    'Uniform 0..99 bucket. Conditions filter_bucket < N match N percent when row count is divisible by 100.';

