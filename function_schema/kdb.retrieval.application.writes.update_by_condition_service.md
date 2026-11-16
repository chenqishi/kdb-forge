# kdb.retrieval.application.writes.update_by_condition_service

## Signature

`async update_by_condition_service(index_name: str, update_fields: Dict[str, Any], conditions: List[Dict[str, Any]]) -> tuple[bool, int, str]`

## Inputs

索引、更新字段字典和 AND 条件列表；调用当前 runtime 的 SearchDataInterface。

## Outputs

成功返回 `(True, updated_count, "条件更新操作完成")`，条数直接来自 update_data_value，0 也成功，不按条数真假判断状态。同值写入计入成功更新数。

异常返回 `(False, 0, message)`，消息保留错误原因并明确可能已有部分写入且不会自动回滚。失败时 0 是未获得完整计数的占位值，不能当作实际零写入。HTTP 响应字段保持 success、updated_count、message。

## SQL

无；通过 SearchDataInterface 调用 ES8 条件更新。

## Source

`src/kdb/retrieval/application/writes.py`。
