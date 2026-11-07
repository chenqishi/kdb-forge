# html_kg_gen_task_control.stage_8_insert_index

## 描述

HTML 任务阶段 8：把 QA search-data 写入目标 ES 索引。任务可通过
`insert_is_need_llm` 覆盖索引配置中的重复知识 LLM 精判开关。

## Inputs

- `self.search_data_file_path`
- `self.index_name`
- `self.insert_is_need_llm`: `None` 时不追加命令行参数；布尔值时追加
  `--is_need_llm=true|false`。
- `self.insert_check_duplicate`: `None` 沿用索引配置；布尔值时追加
  `--check_duplicate=true|false`。

`False` 只关闭外部 LLM 精判，仍保留向量查重和数值阈值规则，不等于关闭查重。
`insert_check_duplicate=False` 才会完全关闭跨库查重；只应用于来源 URL 已去重、且按国家/租户
类目过滤时必须保留独立知识副本的任务。

## Outputs

- `bool`: 入库子命令成功返回 True，否则 False。

## SQL / ES

不直接读写 SQL。通过 `insert_data_to_search_index` 写 `self.index_name` 指定的 ES 索引。
