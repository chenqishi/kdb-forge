# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._scroll_request

## Signature

`EsSearchInterfaceES8._scroll_request(self, client: Any, scroll_id: str, scroll_timeout: str) -> Dict[str, Any]`

## Inputs

ES8 client、scroll_id、scroll 保活时间。

## Outputs

下一页响应；检查超时和 `_shards.failed`，耗尽重试后抛错。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
