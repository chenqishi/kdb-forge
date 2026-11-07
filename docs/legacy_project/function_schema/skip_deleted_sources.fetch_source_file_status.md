# skip_deleted_sources.fetch_source_file_status

## Purpose

按来源文件名批量查 ES，判断这篇文章的知识是不是**已被整篇下架**（软删）。
用于重新灌库前的闸门：人工下架过的文章不再插入新知识。

## Inputs

- `names` (list[str]): `ext_info.from_file_name` 值列表。
- `index_name` (str): ES 索引，默认 `wayfair`。
- `es_config` (str): ES 连接配置路径。

## Outputs

- `dict[str, dict]`：`{name: {'alive': int, 'deleted': int, 'verdict': str, 'flags': [...]}}`

`verdict` 取值：

| 值 | 含义 | 是否插入 |
|---|---|---|
| `all_deleted` | 有软删记录且**活跃条数为 0** —— 整篇被下架 | **跳过** |
| `partial_deleted` | 既有活跃也有软删 —— 通常是入库去重打掉的零星条目，不是下架 | 插入 |
| `never_indexed` | ES 里一条记录都没有 | 插入（并在报告里点名，通常意味着上一轮 QA 没产出） |
| `ok` | 全部活跃 | 插入 |

`flags` 收集软删记录上的 `flag` 字段（批量软删的批次标记），便于追溯是哪一批删的。

## SQL

No SQL access。只读 ES：`ext_info.from_file_name.keyword`、`del_flag`、`flag`。
