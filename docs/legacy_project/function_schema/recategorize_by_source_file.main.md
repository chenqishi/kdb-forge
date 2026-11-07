# main

## 所属文件
`data_control_tools/recategorize_by_source_file.py`

## 功能描述
CLI 入口：按来源文件名把整批知识改挂到指定类目，默认 dry-run，`--execute` 才写。

## Inputs（CLI）
| 参数 | 必填 | 说明 |
|---|---|---|
| `--index` | 是 | ES 索引名，如 `payoneer_olive_payoneer_olive`（私人知识库）|
| `--client` | 是 | 类目树所属 client，如 `payoneer_olive` |
| `--category` | 是 | 目标类目名，会去线上类目树校验存在性；只支持一级类目 |
| `--file-name` | 是 | 可重复，来源文件名精确值 |
| `--task-id` | 否 | 可重复，叠加任务过滤 |
| `--work-dir` | 否 | 明细/回滚落盘目录，默认 `output/recategorize_<index>` |
| `--include-deleted` | 否 | 连软删的一起改 |
| `--execute` | 否 | 真正写 ES |
| `--rollback` | 否 | 传 rollback.jsonl 路径，配合 `--execute` 回滚 |
| `--es-config` | 否 | 默认 `config/config_es_engine.json` |

## Outputs
stdout 打印 JSON 报告（按文件名 × 原类目的条数分布 + 写回结果）；
`--execute` 时先写 `<work-dir>/rollback.jsonl` 再 bulk。

## 复用
`build_category_fields` / `bulk_update_doc` / `run_rollback` 直接 import
`data_control_tools/assign_platform_category.py`，保证 `category_infos` +
`primary_category` 两个结构体的写法和存量回填完全一致。

## SQL
无。
