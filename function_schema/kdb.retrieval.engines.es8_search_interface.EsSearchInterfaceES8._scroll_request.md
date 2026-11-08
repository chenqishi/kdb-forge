# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._scroll_request

## Signature

`_scroll_request(self, client: Any, scroll_id: str, scroll_timeout: str) -> Dict[str, Any]`

## Inputs

ES8 client、scroll_id、scroll 保活时间。

## Outputs

下一页响应；检查超时和 `_shards.failed`，耗尽重试后抛错。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
