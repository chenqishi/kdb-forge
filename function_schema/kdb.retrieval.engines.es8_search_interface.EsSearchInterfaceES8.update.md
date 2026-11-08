# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.update

## Signature

`update(self, data_id: str, data: Dict[str, Any], index_names: IndexNames=None) -> bool`

## Inputs

文档 `_id`、局部字段、目标索引。

## Outputs

所有目标索引通过 ES8 `update(doc=...)` 更新成功返回 True。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
