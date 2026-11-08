# kdb.mining.chat.query_analysis.ecommerce.load_local_sample_rows

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

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
