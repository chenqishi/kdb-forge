# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._single_search_with_retry

## Signature

`_single_search_with_retry(self, index_str: str, body: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

索引名和旧 body 形状查询。

## Outputs

ES8 named-parameter 查询响应；分片失败会按统一策略重试，耗尽抛错。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
