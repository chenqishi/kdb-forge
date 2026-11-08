# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.delete

## Signature

`delete(self, data_id: str, index_names: IndexNames=None, refresh: bool=False) -> bool`

## Inputs

文档 `_id`、目标索引、refresh 标志。

## Outputs

所有目标索引删除成功返回 True。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
