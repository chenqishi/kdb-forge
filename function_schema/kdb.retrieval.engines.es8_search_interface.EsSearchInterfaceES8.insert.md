# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.insert

## Signature

`insert(self, data: Dict[str, Any], index_names: IndexNames=None, refresh_imm: bool=False) -> bool`

## Inputs

含 `_id` 和已生成向量的文档、目标索引、refresh 标志。

## Outputs

所有目标索引通过 ES8 `update(doc=..., doc_as_upsert=True)` upsert 成功返回 True。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
