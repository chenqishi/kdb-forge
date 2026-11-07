# parse_page_range

## 所属文件
`data_control_tools/prune_page_mismatched_images.py`

## 功能描述
从 `ext_info` 取这条知识的页码区间。**QA 和 segment 的字段不一样**。

## Inputs
- `ext_info` (Dict)
- `data_type` (str) — `qa` 或 `segment`

## Outputs
`Optional[Tuple[int,int]]` — 闭区间 `(起, 止)`，取不到返回 None。

## ES schema（实测 wayfair 索引）
| data_type | 页码字段 |
|---|---|
| `qa` | `ext_info.from_page = [起, 止]` |
| `segment` | `ext_info.start_page` / `ext_info.end_page`（整数） |

segment 的 `ext_info` 里**没有 `from_page`**（键是
`end_page` / `from_file_name` / `phrases` / `start_page` / `tags` / `topics`）。
用错字段会导致 segment 全部取不到页码而被跳过，或（若默认放行）全裁光。

## SQL
无。
