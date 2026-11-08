# kdb.mining.chat.query_analysis.ecommerce._split_csv

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

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
