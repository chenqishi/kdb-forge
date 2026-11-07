# kdb.integrations.data_control.prune_page_mismatched_images.parse_page_range

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

`src/kdb/integrations/data_control/prune_page_mismatched_images.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
