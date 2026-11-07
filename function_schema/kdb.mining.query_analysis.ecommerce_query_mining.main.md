# kdb.mining.query_analysis.ecommerce_query_mining.main

## Signature

`main(argv: Optional[Sequence[str]]=None) -> int`

## Description

命令行入口，解析参数并按 `--mode` 调用数据库聚合、随机样本下载或本地样本挖掘流程。

## Inputs

命令行参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| --mode | str | 否 | `db_aggregate`、`download_sample`、`mine_sample`，默认 `db_aggregate` |
| --customers | str | 条件必填 | `db_aggregate/download_sample` 需要，逗号分隔 customer 列表 |
| --start-time | str | 否 | 起始时间 |
| --end-time | str | 否 | 结束时间 |
| --sample-size | int | 否 | `download_sample` 总随机抽样条数 |
| --sample-output-path | str | 否 | `download_sample` JSONL 输出路径 |
| --sample-input-path | str | 条件必填 | `mine_sample` 本地 JSONL 样本输入路径 |
| --random-seed | int | 否 | `download_sample` MySQL RAND seed |
| --per-customer-even / --no-per-customer-even | bool | 否 | `download_sample` 是否按 customer 均分样本 |
| --raw-limit | int | 否 | SQL 聚合候选上限 |
| --max-candidates | int | 否 | 进入泛化候选上限 |
| --max-queries | int | 否 | 最终 query 上限 |
| --batch-size | int | 否 | LLM 批大小 |
| --sample-per-query | int | 否 | 样本数 |
| --model-name | str | 否 | 模型名 |
| --provider | str | 否 | 渠道 |
| --output-dir | str | 否 | 输出目录 |
| --require-reply / --no-require-reply | bool | 否 | 是否要求回复 |
| --skip-llm | bool | 否 | 跳过 LLM |

## Outputs

| 类型 | 说明 |
|------|------|
| int | 进程退出码，成功为 0 |

## SQL

`db_aggregate` 通过 `mine_queries` 只读 `data_chat_history`；`download_sample` 通过 `download_random_sample` 只读 `data_chat_history`；`mine_sample` 无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
