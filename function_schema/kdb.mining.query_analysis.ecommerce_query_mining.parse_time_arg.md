# kdb.mining.query_analysis.ecommerce_query_mining.parse_time_arg

## Signature

`parse_time_arg(value: Optional[str], end_of_day: bool=False) -> Optional[str]`

## Description

把命令行传入的时间参数转换为 MySQL 可比较的 `YYYY-MM-DD HH:MM:SS` 字符串。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| value | str\|None | 否 | 支持 `YYYYMMDDHHMMSS`、`YYYY-MM-DD HH:MM:SS`、`YYYY-MM-DD`；为空返回 `None` |
| end_of_day | bool | 否 | 当输入为日期时是否转为当天 `23:59:59`，默认 `False` |

## Outputs

| 类型 | 说明 |
|------|------|
| str\|None | 标准时间字符串；输入为空时为 `None` |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
