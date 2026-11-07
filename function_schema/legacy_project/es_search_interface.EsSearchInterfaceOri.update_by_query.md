# es_search_interface.EsSearchInterfaceOri.update_by_query

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_search_interface.py`

Inputs: `self, index_name: str, query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int=500`.

Behavior / Outputs: 按 query 批量更新字段（本功能用来写 del_flag=1）。

用 update_by_query 而不是「先查 ID 再逐条更新」：后者要把成千上万条 hits
拉回来，正是会被分片取消静默截断的用法，会导致「以为删完了其实漏了一批」。

conflicts=proceed：并发写入造成的版本冲突不中断整批，冲突数在返回里体现。
requests_per_second：限流，本集群对负载敏感（见 _search_with_shard_check）。

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
