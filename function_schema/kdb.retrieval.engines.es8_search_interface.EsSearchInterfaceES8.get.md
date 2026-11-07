# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.get

## Signature

`EsSearchInterfaceES8.get(self, data_id: str, index_names: IndexNames=None) -> Optional[Dict[str, Any]]`

## Inputs

文档 `_id`、目标索引。

## Outputs

第一个命中的文档，未命中返回 None。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
