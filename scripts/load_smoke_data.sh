#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DB_NAME=${PGDATABASE:-filtered_vector_search}
DB_USER=${PGUSER:-$(id -un)}

if [[ ${USE_DOCKER:-0} == 1 ]]; then
  psql_cmd=(docker compose -f "$ROOT_DIR/compose.yaml" exec -T postgres psql -X -U postgres -d "$DB_NAME")
  items_csv=/data/smoke_items.csv
  queries_csv=/data/smoke_queries.csv
else
  PG_BIN=${PG_BIN:-$ROOT_DIR/.runtime/postgres-17.11/bin}
  if [[ ! -x "$PG_BIN/psql" ]]; then
    echo "psql not found at $PG_BIN/psql; run make postgres-bootstrap or set PG_BIN" >&2
    exit 1
  fi
  export PGHOST=${PGHOST:-127.0.0.1}
  export PGPORT=${PGPORT:-55432}
  export PGUSER=$DB_USER
  export PGDATABASE=$DB_NAME
  psql_cmd=("$PG_BIN/psql" -X -d "$DB_NAME")
  items_csv=$ROOT_DIR/data/generated/smoke_items.csv
  queries_csv=$ROOT_DIR/data/generated/smoke_queries.csv
fi

if [[ ${USE_DOCKER:-0} == 1 ]]; then
  "${psql_cmd[@]}" -v ON_ERROR_STOP=1 < "$ROOT_DIR/sql/001_schema.sql"
else
  "${psql_cmd[@]}" -v ON_ERROR_STOP=1 -f "$ROOT_DIR/sql/001_schema.sql"
fi
"${psql_cmd[@]}" -v ON_ERROR_STOP=1 -c \
  "\\copy smoke_items (id, filter_bucket, source_label, embedding) FROM '$items_csv' WITH (FORMAT csv, HEADER true)"
"${psql_cmd[@]}" -v ON_ERROR_STOP=1 -c \
  "\\copy smoke_queries (query_id, embedding) FROM '$queries_csv' WITH (FORMAT csv, HEADER true)"
if [[ ${USE_DOCKER:-0} == 1 ]]; then
  "${psql_cmd[@]}" -v ON_ERROR_STOP=1 < "$ROOT_DIR/sql/002_indexes.sql"
else
  "${psql_cmd[@]}" -v ON_ERROR_STOP=1 -f "$ROOT_DIR/sql/002_indexes.sql"
fi

"${psql_cmd[@]}" -At -c \
  "SELECT 'loaded_rows=' || count(*) FROM smoke_items; SELECT 'loaded_queries=' || count(*) FROM smoke_queries;"
