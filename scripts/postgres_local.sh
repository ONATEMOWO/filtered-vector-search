#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PG_BIN=${PG_BIN:-$ROOT_DIR/.runtime/postgres-17.11/bin}
PGDATA=${PGDATA:-$ROOT_DIR/.runtime/data}
# macOS limits Unix-domain socket paths to 103 bytes. The repository can live
# under a long path, so use a short, user-specific socket directory by default.
PGSOCKET=${PGSOCKET:-/private/tmp/filtered-vector-search-$(id -u)}
PGLOG=${PGLOG:-$ROOT_DIR/.runtime/postgres.log}
PGPORT=${PGPORT:-55432}
PGUSER=${PGUSER:-$(id -un)}
PGDATABASE=${PGDATABASE:-filtered_vector_search}

if [[ ! -x "$PG_BIN/postgres" ]]; then
  echo "PostgreSQL runtime not found; run ./scripts/bootstrap_postgres_macos.sh" >&2
  exit 1
fi

export PGHOST=127.0.0.1 PGPORT PGUSER PGDATABASE

initialize() {
  if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
    mkdir -p "$PGDATA" "$PGSOCKET"
    LC_ALL=C "$PG_BIN/initdb" \
      --pgdata="$PGDATA" \
      --username="$PGUSER" \
      --encoding=UTF8 \
      --locale=C \
      --auth-local=trust \
      --auth-host=trust
  fi
}

start() {
  initialize
  mkdir -p "$PGSOCKET"
  if ! "$PG_BIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
    "$PG_BIN/pg_ctl" -D "$PGDATA" -l "$PGLOG" \
      -o "-p $PGPORT -k $PGSOCKET -c listen_addresses=127.0.0.1" -w start
  fi
  if ! "$PG_BIN/psql" -X -d postgres -Atqc \
      "SELECT 1 FROM pg_database WHERE datname = '$PGDATABASE'" | grep -qx 1; then
    "$PG_BIN/createdb" "$PGDATABASE"
  fi
  echo "PostgreSQL is ready: host=$PGHOST port=$PGPORT user=$PGUSER database=$PGDATABASE"
}

stop() {
  if [[ -f "$PGDATA/PG_VERSION" ]] && "$PG_BIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
    "$PG_BIN/pg_ctl" -D "$PGDATA" -m fast -w stop
  else
    echo "PostgreSQL is not running"
  fi
}

status() {
  "$PG_BIN/pg_ctl" -D "$PGDATA" status
}

case ${1:-} in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
