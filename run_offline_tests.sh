#!/usr/bin/env bash
set -euo pipefail
kdb_test_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "${KDB_TEST_PYTHON:-python3}" "$kdb_test_root/scripts/testing/offline_runner.py" "$@"
