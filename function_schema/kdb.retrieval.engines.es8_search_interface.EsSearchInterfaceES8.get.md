# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.get

## Signature

`get(self, data_id: str, index_names: IndexNames=None) -> Optional[Dict[str, Any]]`

## Inputs

文档 `_id`、目标索引。

## Outputs

第一个命中的文档，未命中返回 None。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
