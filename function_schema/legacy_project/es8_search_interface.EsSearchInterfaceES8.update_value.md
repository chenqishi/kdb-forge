# EsSearchInterfaceES8.update_value

## 2026-10-05 del_flag repair contract

Inputs: unchanged index_name/update_value_dict/conditions with AND semantics. Outputs: True for complete success/empty patch; False on API/terminal error/conflict/partial failure. Mapping guard stays outside exception fallback. Serverless no scripts, PaaS original native update; no public signature changes or SQL.

## References
Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

## 2026-10-08 integration
Port into the current old-project baseline, preserving service/API/business source and existing mappings/configuration. Offline verification only; no real writes or deployment.
