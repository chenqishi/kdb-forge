# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._single_search_with_retry

## Signature

`EsSearchInterfaceES8._single_search_with_retry(self, index_str: str, body: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

索引名和旧 body 形状查询。

## Outputs

ES8 named-parameter 查询响应；分片失败会按统一策略重试，耗尽抛错。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
