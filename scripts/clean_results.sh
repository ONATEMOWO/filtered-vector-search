#!/usr/bin/env bash
set -euo pipefail

echo "clean-results is disabled: raw_results contains versioned Milestone 1 evidence" >&2
echo "and append-only Milestone 2 run artifacts. Remove an exact untracked run only" >&2
echo "after reviewing its path and preservation requirements." >&2
exit 2
