# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._search_once_with_retry

## Signature

`EsSearchInterfaceES8._search_once_with_retry(self, search_index: str, body: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

索引名和旧 body 形状查询。

## Outputs

经过分片失败检查与重试的响应。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
