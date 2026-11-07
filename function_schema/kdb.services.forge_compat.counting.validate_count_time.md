# kdb.services.forge_compat.counting.validate_count_time

## Signature

`validate_count_time(value: Optional[str]) -> Optional[str]`

## Inputs

`value: Optional[str]`：本地时间，严格 `yyyy-MM-dd HH:mm:ss`。

## Outputs

`None` 表示未提供；合法日历时间原样返回，包含四位年份 `0001`。
空串、格式错误、非法日历日期/时刻或非字符串抛 `ValueError`。
单边时间同样校验；不转换时区、不 trim。

## SQL

无；纯本地函数。

## Source

`src/kdb/services/forge_compat/counting.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
