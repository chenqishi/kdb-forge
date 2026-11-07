# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._search_with_shard_check

## Signature

`EsSearchInterfaceES8._search_with_shard_check(self, search_index: str, body: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

旧 body 形状的 search DSL，包含 `query`、`from`、`size`、`_source`、`sort`、`aggs` 等字段。

## Outputs

转换为 ES8 named search 参数后返回标准字典响应；不向 ES8 client 传递 `body=`。

## SQL

无；读取 Elasticsearch。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
