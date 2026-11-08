# kdb.mining.chat.query_analysis.align_gaps.main

## Signature

`main()`

## Inputs

`--gap-csv` must explicitly identify the input CSV, unless `KDB_GAP_CSV` supplies its default. No former workspace/document directory default is retained. All other existing CLI flags and input CSV shape remain unchanged.

## Outputs

Parse the same inputs and execute the unchanged matching/retrieval/report logic. Missing input configuration fails in argparse before reading files or initializing clients.

## SQL

No SQL/ES query/schema change. This migration only removes a hardcoded external checkout input path.

## Source

`src/kdb/mining/chat/query_analysis/align_gaps.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
