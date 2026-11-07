# EsSearchInterfaceES8._update_without_script

## 2026-10-05 del_flag repair contract

Inputs: client, original physical index names, raw query, update_fields, rps, abort/proceed. Outputs: synchronous updated/total/version_conflicts/failures. Serverless full-source query updates use PIT snapshot, latest PIT ID, exact total, <=50 hit pages, <=8MiB bulk chunks, complete source CAS index writes and original routing. Same-value assignments are reindexed/updated as legacy script, never silent noop; no auto overwrite retry. Abort conflicts/nonconflict bulk failures/incomplete query/result must raise, successful prefix not rolled back. Each hit requires source, index, ID, seq_no, term, cursor; validate before writing that page. Latest PIT closes finally. No SQL, alias/name/config changes; real writes tested only in approved isolated scope.

## References
Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

Serialization uses elasticsearch.serializer.JSONSerializer (the same class exported by ES8.17 root package, identity verified locally). Import the defining module so unrelated test replacement of the root module does not hide the real serializer. This does not replace client/dependencies or relax scope.

## 2026-10-08 integration
Port into the current old-project baseline, preserving service/API/business source and existing mappings/configuration. Offline verification only; no real writes or deployment.

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es8_search_interface.py`

Inputs: `self, client: Any, indexes: Sequence[str], query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int, conflicts: str`.

Behavior / Outputs: Snapshot + full-source CAS preserves script assignment semantics.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
