#!/usr/bin/env bash
kdb_candidate_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
exec "$kdb_candidate_root/control_script/timing_run_task_gen_knowledge_by_send_request.sh" "$@"
