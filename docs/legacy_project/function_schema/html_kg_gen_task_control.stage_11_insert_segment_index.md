# html_kg_gen_task_control.stage_11_insert_segment_index

## 描述

HTML 任务阶段 11：把 segment search-data 写入目标 ES 索引。与 QA 入库一致，任务可通过
`insert_is_need_llm` 覆盖重复知识 LLM 精判开关。

## Inputs

- `self.segment_search_data_file_path`
- `self.index_name`
- `self.insert_is_need_llm`: `None` 沿用索引配置；布尔值追加
  `--is_need_llm=true|false`。
- `self.insert_check_duplicate`: `None` 沿用索引配置；布尔值追加
  `--check_duplicate=true|false`。关闭时由显式 URL 清单和确定性文档 ID 控制重复。

## Outputs

- `bool`: 入库子命令成功返回 True，否则 False。

## SQL / ES

不直接读写 SQL。通过 `insert_data_to_search_index` 写 `self.index_name` 指定的 ES 索引。
