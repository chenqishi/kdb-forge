# kdb.retrieval.maintenance.prune_mismatched_images.parse_page_range

## Signature

`parse_page_range(ext_info: Dict[str, Any], data_type: str) -> Optional[Tuple[int, int]]`

## Description

从 `ext_info` 取这条知识的页码区间。**QA 和 segment 的字段不一样**。

## Inputs

- `ext_info` (Dict)
- `data_type` (str) — `qa` 或 `segment`

## Outputs

`Optional[Tuple[int,int]]` — 闭区间 `(起, 止)`，取不到返回 None。

## SQL

无。

## Source

`src/kdb/retrieval/maintenance/prune_mismatched_images.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
