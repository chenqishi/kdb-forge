# extract_urls_from_excel

## 所属文件
`knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`

## 功能
从 Excel 工作簿中提取**单元格超链接目标**（`cell.hyperlink.target`），而不是单元格显示值。

Wayfair 开发者门户的 URL 清单
（`开发者门户上传260805.xlsx`）里，单元格值是 `1. Introduction`、`Graph QL` 这类人读标签，
真正的 URL 只存在于 openpyxl 的 `cell.hyperlink.target` 上。直接读 `cell.value` 会一个 URL 都拿不到。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| excel_path | str | 是 | - | `.xlsx` 路径 |
| sheet_name | str | 否 | `None` | 指定工作表；`None` 表示遍历全部工作表 |

## Outputs
| 类型 | 说明 |
|------|------|
| list[dict] | 每项 `{"label": str, "url": str, "cell": str, "sheet": str}`，按单元格出现顺序 |

- `label`：`cell.value` 去首尾空白后的文本；单元格无值时为 `""`
- `url`：`cell.hyperlink.target`
- 无 `hyperlink` 的单元格直接跳过（如 `7. CastleGate API` 这类纯分组标题行）
- 同一 URL 若出现多次，按出现顺序全部返回，去重交给调用方

## 逻辑说明
1. `openpyxl.load_workbook(excel_path)`（默认 `data_only=False`，超链接才会被保留）
2. 遍历目标工作表的 `ws.iter_rows()`
3. `cell.hyperlink` 为 `None` 或 `cell.hyperlink.target` 为空则跳过
4. 返回有序列表

## 依赖的外部接口
无。仅 `openpyxl`。

## SQL
无。
