# plan_recategorize

## 所属文件
`data_control_tools/recategorize_by_source_file.py`

## 功能描述
为圈定的知识生成写回计划：目标类目统一是 CLI 指定的那一个，只有当前类目与目标不同的才算 `changed`。

## Inputs
- `docs` — `download_targets` 产物，每条含 `_id` / `title` / `from_file_name` /
  `old_category`（取自 `primary_category.category_path`，缺失为 `''`）/
  `old_category_infos` / `old_primary_category`
- `category_name` (str) — 目标类目名。**当前只支持一级类目**：复用的 `build_category_fields`
  只写 `cate1_*`，二级路径（`Mercado Libre-入驻指引`）会丢层级，`load_category_id` 里直接挡掉
- `category_id` (str) — 目标类目 id，来自线上类目树，不允许硬编码传入未校验的值

## Outputs
`List[Dict]`，在输入基础上加 `new_category` / `category_id` / `changed`。

## 与 assign_platform_category 的区别
那个脚本从 title 猜平台，这个脚本**不猜**：目标类目由人指定，圈定范围由文件名/任务 id 指定。
适用场景是「文档挖掘任务投递时 `category_id` 填错了，整批知识挂错组」——
这种错误 title 里没有任何信号，猜不出来。

## SQL
无。
