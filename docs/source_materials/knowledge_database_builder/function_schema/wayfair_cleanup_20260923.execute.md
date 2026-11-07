# wayfair_cleanup_20260923.execute

## Inputs
Immutable `final_delete_ids.json` (6,205 IDs), prior old/new snapshots, mapping and recheck evidence. User confirmed 2026-09-23 to run the existing machine-audit script with a one-hour age threshold and continue planned deletion.

## Outputs
Fresh audit state and deletion preflight, exact execution IDs, prewrite rollback fields, write responses and post-verification. Additional records may be retained, never added to the authorized manifest.

## ES / SQL
Only index `wayfair`; no SQL. Existing `AutoAuditProcessor` uses high -> audit_result=2 and non-high QA -> 0; non-high segments remain pending by design. Before deletion require all 8 update tasks' high records approved, non-high QA processed; every replacement file has approved records. For low-confidence files require at least one approved evidence record per substantive covered sample, otherwise protect whole old file.

Delete using existing `_run_update_by_query`, exact ID query AND del_flag=0 AND old marker AND old filename scope AND insert_time before new generation, excluding nine new tasks and all protected filenames. Script changes only `del_flag=1`. Existing serverless write-limit reduction and asynchronous task polling are reused. Write fresh delta rollback before mutation, compare live source with backup; abort on unexpected changes. Post-verify candidate IDs deleted, retained original IDs active, all nine new-task baseline IDs active and unchanged apart from the authorized audit_result.

No code deployment, restart, global cron modification, commit, push, physical deletion, or general filename deletion. `--hours 1` applies to this invocation; global default is not broadened to other clients.

Two previously cited QA records are mid-quality. Their fully equivalent high-quality source segments were explicitly read: F22S1 -> a9676470f549823047dfb4356a14fd17 (variant definition, attributes, same product-detail page), F29S2 -> 0f9b01c6aa786edf5e51d3b28a059429 (existing suppliers automatically enter advanced access). Preflight re-fetches these exact clean new records, requires approval and unchanged body, and records supplemental evidence. This does not approve/rewrite knowledge or broaden deletion scope.
