# build_target_query

## 所属文件
`data_control_tools/recategorize_by_source_file.py`

## 功能描述
构造「按来源文件名 / 任务 id 圈定待改组知识」的 ES 查询。

## Inputs
- `file_names` (List[str]) — `ext_info.from_file_name` 精确值列表（term，大小写和空格必须完全一致）
- `task_ids` (List[str], 可空) — 再叠加 `task_id` 过滤；用于「同一份文件被多个任务处理过，
  只改其中某个任务产出的那批」
- `include_deleted` (bool, 默认 False) — 是否连 `del_flag=1`（软删）的一起改

## Outputs
`Dict` — ES query：`bool.filter` = `[terms(ext_info.from_file_name.keyword), (terms(task_id)), (term del_flag=0)]`

## 字段说明
- `ext_info.from_file_name` 是 text，**必须用 `.keyword` 子字段**做 term 精确匹配
- `task_id` 本身就是 keyword 类型，**没有 `.keyword` 子字段**（用 `task_id.keyword` 聚合会返回空桶）

## SQL
无。
