#!/usr/bin/env bash
kdb_candidate_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
exec "$kdb_candidate_root/control_script/timing_auto_audit_all_indexes.sh" "$@"
