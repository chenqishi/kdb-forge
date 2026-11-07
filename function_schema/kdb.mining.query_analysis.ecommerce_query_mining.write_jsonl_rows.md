# kdb.mining.query_analysis.ecommerce_query_mining.write_jsonl_rows

## Signature

`write_jsonl_rows(output_path: str, rows: Sequence[dict]) -> str`

## Description

将数据库抽样得到的聊天记录写为本地 JSONL 文件，作为后续离线挖掘的固定样本池。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| output_path | str | 是 | JSONL 输出路径 |
| rows | list[dict] | 是 | 聊天记录行 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 写出的 JSONL 路径 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
