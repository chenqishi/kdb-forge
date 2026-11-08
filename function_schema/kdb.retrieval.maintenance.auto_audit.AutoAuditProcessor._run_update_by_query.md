# kdb.retrieval.maintenance.auto_audit.AutoAuditProcessor._run_update_by_query

## Signature

`_run_update_by_query(self, index_name: str, query: Dict[str, Any], update_fields: Dict[str, Any], scroll_size: int, request_timeout_seconds: int=3600) -> Dict[str, Any]`

## Inputs

index_name、query、update_fields、scroll_size、request_timeout_seconds=3600。

## Outputs

先对当前 engine 配置维护更新批量与超时，再返回 engine.update_by_query 的验证结果。无独立客户端或私有任务轮询；未知写入结果不自动重放。

## SQL

无 SQL；ES update_by_query，目标索引与字段赋值来自调用参数，完整性/异步处理由 retrieval/engines/es_maintenance.py 执行。

## Source

`src/kdb/retrieval/maintenance/auto_audit.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
