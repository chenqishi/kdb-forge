# kdb.mining.query_analysis.gap_material_coverage.main

## Signature

`main()`

## Inputs

`--gap-csv` must explicitly identify the input CSV, unless `KDB_GAP_CSV` supplies its default. No former workspace/document directory default is retained. All other existing CLI flags and input CSV shape remain unchanged.

## Outputs

Parse the same inputs and execute the unchanged matching/retrieval/report logic. Missing input configuration fails in argparse before reading files or initializing clients.

## SQL

No SQL/ES query/schema change. This migration only removes a hardcoded external checkout input path.

## Source

`src/kdb/mining/query_analysis/gap_material_coverage.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
