# EsSearchInterfaceES8._apply_source_assignments

## 2026-10-05 del_flag repair contract

Inputs: complete stored-source Mapping and ordered update_fields. Outputs: a deep copied full source with legacy Painless assignment semantics: top-level objects/arrays replace, dotted paths traverse existing dictionaries only; missing/nonobject/nested-list parent fails explicitly, no fabricated parent/no list overwrite. Caller source/patch untouched; no persistence or SQL.

## References
Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

## 2026-10-08 integration
Port into the current old-project baseline, preserving service/API/business source and existing mappings/configuration. Offline verification only; no real writes or deployment.
