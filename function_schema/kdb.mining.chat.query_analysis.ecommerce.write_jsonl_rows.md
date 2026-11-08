# kdb.mining.chat.query_analysis.ecommerce.write_jsonl_rows

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

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
