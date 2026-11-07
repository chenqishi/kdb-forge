# EsSearchInterfaceES8.update_by_query

## 2026-10-05 del_flag repair contract

Inputs: unchanged index/query/update_fields/rps. Outputs: unchanged four statistics keys for success/proceed conflicts. Terminal errors and nonconflict failure raise RuntimeError so unchanged delete_by_file cannot report success on failure. Serverless safe no-script snapshot+CAS, PaaS native path; partial successes not rolled back. No SQL.

## References
Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

## 2026-10-08 integration
Port into the current old-project baseline, preserving service/API/business source and existing mappings/configuration. Offline verification only; no real writes or deployment.
