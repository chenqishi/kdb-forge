# kdb.retrieval.maintenance.retire_superseded.load_snapshot_ids

## Signature

`load_snapshot_ids(snapshot_file: str) -> List[str]`

## Description

读取「插入新数据之前落的 _id 快照」，返回去重排序的 `_id` 列表。

## Inputs

- `snapshot_file` (str) — 快照路径。两种格式都吃：
  - JSON 数组，元素是 dict 且含 `_id`（`wf_snap_old_qa.py` 那类盘点脚本的产物）
  - 每行一个 `_id` 的纯文本

## Outputs

`List[str]` — 排序去重后的 `_id`。

## SQL

无。ES 侧不读不写。

## Source

`src/kdb/retrieval/maintenance/retire_superseded.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
