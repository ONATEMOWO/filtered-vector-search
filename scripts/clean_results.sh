#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
find "$ROOT_DIR/raw_results" -type f ! -name '.gitkeep' -delete
echo "removed generated files below raw_results/"

