# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.insert

## Signature

`EsSearchInterfaceES8.insert(self, data: Dict[str, Any], index_names: IndexNames=None, refresh_imm: bool=False) -> bool`

## Inputs

含 `_id` 和已生成向量的文档、目标索引、refresh 标志。

## Outputs

所有目标索引通过 ES8 `update(doc=..., doc_as_upsert=True)` upsert 成功返回 True。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
