# kdb.services.forge_compat.counting.validate_count_from_type

## Signature

`validate_count_from_type(value: str) -> str`

## Inputs

`value: str`：调用方传入的来源值。

## Outputs

非空字符串原样返回；空串或非字符串抛 `ValueError`。
不 trim、不做规则映射、不替换为 `from_type_norm`。

## SQL

无；纯本地函数。

## Source

`src/kdb/services/forge_compat/counting.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
