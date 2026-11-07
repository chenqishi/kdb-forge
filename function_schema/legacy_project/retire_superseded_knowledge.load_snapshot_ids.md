# load_snapshot_ids

## 所属文件
`data_control_tools/retire_superseded_knowledge.py`

## 功能描述
读取「插入新数据之前落的 _id 快照」，返回去重排序的 `_id` 列表。

## Inputs
- `snapshot_file` (str) — 快照路径。两种格式都吃：
  - JSON 数组，元素是 dict 且含 `_id`（`wf_snap_old_qa.py` 那类盘点脚本的产物）
  - 每行一个 `_id` 的纯文本

## Outputs
`List[str]` — 排序去重后的 `_id`。

## SQL
无。ES 侧不读不写。
