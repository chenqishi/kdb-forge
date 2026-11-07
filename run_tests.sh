#!/usr/bin/env bash
# Safe default. Original real-integration runner is archived as non-executable text.
set -euo pipefail
kdb_test_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$kdb_test_root/run_offline_tests.sh" "$@"
