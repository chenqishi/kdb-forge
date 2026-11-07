# kdb.mining.query_analysis.ecommerce_query_mining.load_local_sample_rows

## Signature

`load_local_sample_rows(sample_path: str) -> List[dict]`

## Description

从本地 JSONL 样本文件读取聊天记录，供离线挖掘使用。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sample_path | str | 是 | JSONL 样本路径 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 本地样本记录 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
