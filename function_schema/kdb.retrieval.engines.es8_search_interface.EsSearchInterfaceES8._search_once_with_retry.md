# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._search_once_with_retry

## Signature

`_search_once_with_retry(self, search_index: str, body: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

索引名和旧 body 形状查询。

## Outputs

经过分片失败检查与重试的响应。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
