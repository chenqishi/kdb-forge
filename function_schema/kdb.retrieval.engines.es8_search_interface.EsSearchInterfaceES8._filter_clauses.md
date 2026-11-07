# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._filter_clauses

## Signature

`EsSearchInterfaceES8._filter_clauses(cls, query: Mapping[str, Any], include_default_del_flag: bool=True) -> List[Dict[str, Any]]`

## Inputs

通用 query dict、是否自动加 `del_flag=0`。

## Outputs

时间、属性、软删除过滤子句。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
