# kdb.mining.query_analysis.ecommerce_query_mining._split_csv

## Signature

`_split_csv(value: Optional[str]) -> List[str]`

## Description

把命令行逗号分隔参数拆为去空白后的字符串列表。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| value | str\|None | 否 | 逗号分隔文本 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[str] | 非空条目列表 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
