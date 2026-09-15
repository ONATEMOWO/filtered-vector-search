#!/usr/bin/env bash
set -euo pipefail

# Pinned, project-local PostgreSQL distribution for macOS. Postgres.app includes
# pgvector; nothing is installed globally and .runtime/ is gitignored.
POSTGRES_APP_VERSION=2.9.6
POSTGRES_MAJOR=17
POSTGRES_VERSION=17.11
DMG_SHA256=b38bb00b8c8702a568270aab85995c550f7f93d1503b818efdc5ff9a519b7168
SEVEN_ZIP_VERSION=26.03
SEVEN_ZIP_SHA256=5ca87677072c59f5602e5c49baa27d4694bacd2259b4e507f0094249d4281480

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RUNTIME_ROOT=$ROOT_DIR/.runtime
RUNTIME_DIR=$RUNTIME_ROOT/postgres-$POSTGRES_VERSION
DMG_NAME=Postgres-$POSTGRES_APP_VERSION-$POSTGRES_MAJOR.dmg
DMG_URL=https://github.com/PostgresApp/PostgresApp/releases/download/v$POSTGRES_APP_VERSION/$DMG_NAME

if [[ -x "$RUNTIME_DIR/bin/postgres" ]]; then
  "$RUNTIME_DIR/bin/postgres" --version
  echo "runtime already present at $RUNTIME_DIR"
  exit 0
fi

mkdir -p "$RUNTIME_ROOT/downloads"
DMG_PATH=$RUNTIME_ROOT/downloads/$DMG_NAME
if [[ ! -f "$DMG_PATH" ]]; then
  curl -fL --retry 3 -o "$DMG_PATH" "$DMG_URL"
fi

actual_sha=$(LC_ALL=C openssl dgst -sha256 "$DMG_PATH" | awk '{print $NF}')
if [[ "$actual_sha" != "$DMG_SHA256" ]]; then
  echo "Postgres.app checksum mismatch: expected $DMG_SHA256, got $actual_sha" >&2
  exit 1
fi

temp_dir=$(mktemp -d "$RUNTIME_ROOT/bootstrap.XXXXXX")
mount_dir=$temp_dir/mount
mkdir -p "$mount_dir" "$RUNTIME_DIR"
mounted=0
cleanup() {
  if [[ $mounted == 1 ]]; then
    hdiutil detach "$mount_dir" >/dev/null 2>&1 || true
  fi
  rm -rf "$temp_dir"
}
trap cleanup EXIT

if hdiutil attach -readonly -nobrowse -mountpoint "$mount_dir" "$DMG_PATH" >/dev/null 2>&1; then
  mounted=1
  ditto "$mount_dir/Postgres.app/Contents/Versions/$POSTGRES_MAJOR" "$RUNTIME_DIR"
  hdiutil detach "$mount_dir" >/dev/null
  mounted=0
else
  # Some sandboxed shells cannot attach disk images. 7-Zip can extract the HFS
  # payload without mounting it. Exit status 2 is accepted only because 7-Zip
  # rejects unrelated PostGIS convenience symlinks that are not needed here.
  seven_zip_archive=$temp_dir/7z2603-mac.tar.xz
  seven_zip_dir=$temp_dir/7zip
  extracted_dir=$temp_dir/extracted
  curl -fL --retry 3 -o "$seven_zip_archive" \
    "https://github.com/ip7z/7zip/releases/download/$SEVEN_ZIP_VERSION/7z2603-mac.tar.xz"
  actual_7z_sha=$(LC_ALL=C openssl dgst -sha256 "$seven_zip_archive" | awk '{print $NF}')
  if [[ "$actual_7z_sha" != "$SEVEN_ZIP_SHA256" ]]; then
    echo "7-Zip checksum mismatch: expected $SEVEN_ZIP_SHA256, got $actual_7z_sha" >&2
    exit 1
  fi
  mkdir -p "$seven_zip_dir" "$extracted_dir"
  LC_ALL=C tar -xJf "$seven_zip_archive" -C "$seven_zip_dir"
  set +e
  "$seven_zip_dir/7zz" x -y -o"$extracted_dir" "$DMG_PATH"
  extract_status=$?
  set -e
  if [[ $extract_status != 0 && $extract_status != 2 ]]; then
    echo "7-Zip failed with status $extract_status" >&2
    exit "$extract_status"
  fi
  source_dir=$extracted_dir/Postgres-$POSTGRES_APP_VERSION-$POSTGRES_MAJOR/Postgres.app/Contents/Versions/$POSTGRES_MAJOR
  if [[ ! -x "$source_dir/bin/postgres" ]]; then
    echo "PostgreSQL binary was not found after DMG extraction" >&2
    exit 1
  fi
  cp -R "$source_dir/". "$RUNTIME_DIR/"
fi

# Removing downloaded-file attributes and ad-hoc signing only the command-line
# entry points makes the relocated binaries executable outside Postgres.app.
xattr -cr "$RUNTIME_DIR"
for command_name in postgres initdb pg_ctl psql createdb dropdb pg_isready pg_config; do
  codesign --force --sign - "$RUNTIME_DIR/bin/$command_name" >/dev/null
done

"$RUNTIME_DIR/bin/postgres" --version
echo "installed project-local runtime at $RUNTIME_DIR"

