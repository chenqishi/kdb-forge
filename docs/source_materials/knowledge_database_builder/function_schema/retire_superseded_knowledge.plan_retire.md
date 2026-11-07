# plan_retire

## 所属文件
`data_control_tools/retire_superseded_knowledge.py`

## 功能描述
把快照名单分成「该软删」和三类「跳过」，是这个工具唯一的判断逻辑，纯函数、可单测。

## Inputs
- `state` (Dict[str, Dict]) — `fetch_current_state` 的返回
- `snapshot_ids` (List[str])
- `new_since` (Optional[str]) — 本轮新数据的最早 `insert_time`，形如 `"2026-09-03 00:00:00"`

## Outputs
`(to_delete, skipped)`：
- `to_delete` (List[str])
- `skipped` (Dict[str, List[str]])，三个 key：`missing` / `already_del` / `overwritten`

## 三条跳过规则的来由
- `already_del`：已经是 `del_flag=1` 的**不重打标**。它们通常带着别的批次的 `flag`，
  覆盖掉等于抹掉那批的来源（见 memory `kb-batch-softdelete-convention`）。
- `overwritten`：`insert_data` 对内容完全相同的条目是**同 `_id` 覆盖写**，
  快照里会有一部分 `_id` 已经被新数据占用。实测 wayfair 任务 `74256b78...`
  4957 条快照里有约 30 条这样被覆盖。不排除就会把刚插进去的新知识删掉。
  判据用 `insert_time >= new_since`（字符串比较即可，格式定长）。
- `missing`：快照之后文档已不在索引里，没什么可删的。

## SQL
无。

## 测试
`tests/test_retire_superseded_knowledge.py`
