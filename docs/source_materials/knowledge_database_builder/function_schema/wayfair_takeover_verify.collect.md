# wayfair_takeover_verify.collect

## Purpose
Read-only recovery evidence for the eight already submitted September 2026 Wayfair document tasks. No ingestion, audit, deletion, refresh, mapping updates, deployment, or task submission.

## Inputs
Existing Claude scratchpad `submitted_tasks.json`, `wf_mapping_final.json`, and `upload_files.json`; repository `config/config_es_engine.json` (credentials never copied to output).

## Outputs
New local evidence directory: ES mapping, full selected source records without vectors, before/after count reconciliation, task/file aggregate report and CSV. Refuse an existing export destination.

## SQL / ES schema
No SQL. Read `wayfair` only via `commons.es_http_client.EsHttpClient.search/count/iter_search_after`. Source fields: task_id (actual mapping text + keyword), data_type (keyword), del_flag, audit_result, quality_level, title, content, ext_info, insert_time, update_time, flag, from_type_norm, multimodal_contents. Scope: union of submitted task IDs, mapped new/old filenames, and the old marker `ext_info.flag=wayfair_update_20260922_old`.

## Invariants
Validate every shard response; use pages of 200; reconcile unique exported IDs against counts before and after. Current task IDs define new output; compare the original filename-minus-old-marker calculation separately. QA max(from_page) vs segment max(end_page) gap >=3 is only a screen, not proof of completeness. Preserve missing-page and zero-QA conditions explicitly.

## Additional acceptance artifacts
`analyze.py` exports source coverage, content-ID reconciliation and old DOCX comparison; `final_live_check.py` repeats read-only task_info / ES count checks. `build_report.py` composes a local Markdown report and anomaly CSV from preserved evidence. The reporting script does not authorize or perform repairs. Calendar stage comparison reads existing raw/quality JSON; it does not invoke quality review or change audit_result. Production/source SHA-256 checks use read-only remote file reads.
