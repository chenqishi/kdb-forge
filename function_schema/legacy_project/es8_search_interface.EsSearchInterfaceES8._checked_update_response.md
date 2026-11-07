# EsSearchInterfaceES8._checked_update_response

## 2026-10-05 del_flag repair contract

Inputs: synchronous update-by-query dict/ObjectApiResponse, including completed task envelopes. Outputs: validated statistics, unwrap completed response; raise RuntimeError on terminal error, timeout, incomplete task, malformed/missing counters or failures. Preserve conflicts=proceed counts. No failure reason/source/credentials in error message; log error type only. No SQL.

## References
Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

## 2026-10-08 integration
Port into the current old-project baseline, preserving service/API/business source and existing mappings/configuration. Offline verification only; no real writes or deployment.
