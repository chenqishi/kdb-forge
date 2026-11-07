# wayfair_cleanup_20260923.prepare

## Inputs
Recovered 391-file mapping and 8 submitted tasks; 64 manually uploaded new documents and their existing task; latest 120-sample recheck (116 substantive samples).

## Outputs
Immutable execution directory containing live old-flag snapshot, exact candidate IDs, protected IDs/files, all unmapped updated files, duplicate-upload verification, current audit distributions and manifest hash.

## ES / SQL
Read only `wayfair`: active `del_flag=0`, `ext_info.flag.keyword=wayfair_update_20260922_old`; export `_id`, task, times, audit, quality, title, content, ext_info. No SQL writes. Backup sufficient for rollback of the sole proposed mutation `del_flag:0 -> 1`; embeddings are unchanged and omitted.

## Scope
Exclude entire old filename if any substantive sample is partial, changed, archived or not_found. Ignore four empty/invalid old samples, which were supplemented with substantive samples. Exclude all nine new task IDs irrespective of inherited flag; exclude records inserted on/after 2026-09-23. IDs must belong to recovered old filename mapping. No mutations during preparation. Deletion requires resolution of the user-specified audit-client conflict and prior audit condition.

Final manifest additionally retains the independently confirmed incomplete replacements from the acceptance report: compliance resource center, PMP bulk upload, kits/composites tickets and material management, plus the unresolved EU promotion-calendar QA quality issue. The product-display ticket file is already included in the 23 low-confidence holds. These are explicit known issues, not an assumption that every damaged HTML tail loses business content. The initial candidate manifest remains preserved; execution may only use `final_delete_ids.json` after live validation.
