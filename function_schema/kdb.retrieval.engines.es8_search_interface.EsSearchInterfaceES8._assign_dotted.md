# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._assign_dotted

## Signature

`EsSearchInterfaceES8._assign_dotted(payload: Dict[str, Any], field: str, value: Any) -> None`

## Inputs

目标 JSON、点号字段名、值。

## Outputs

无返回；原地写入 nested JSON，不生成 literal dotted key。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
