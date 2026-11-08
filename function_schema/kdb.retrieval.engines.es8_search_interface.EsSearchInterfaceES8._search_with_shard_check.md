# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._search_with_shard_check

## Signature

`_search_with_shard_check(self, search_index: str, body: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

旧 body 形状的 search DSL，包含 `query`、`from`、`size`、`_source`、`sort`、`aggs` 等字段。

## Outputs

转换为 ES8 named search 参数后返回标准字典响应；不向 ES8 client 传递 `body=`。

## SQL

无；读取 Elasticsearch。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
