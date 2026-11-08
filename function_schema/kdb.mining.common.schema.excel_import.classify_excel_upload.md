# kdb.mining.common.schema.excel_import.classify_excel_upload

## Signature

`classify_excel_upload(excel_file: str, sample_row_limit: int=5) -> Dict[str, Any]`

## Description

统一的 Excel 上传识别/路由函数（deterministic，不调用 LLM）。读取首个含表头的 sheet 的表头与若干样本行，判定该 Excel 应走哪条处理链路。供 `excel_qa_segment_upload_control.py` 在下载文件后做自动路由。

## Inputs

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| excel_file | str | 是 | - | 本地 Excel 路径（.xlsx/.xls），可含空格 |
| sample_row_limit | int | 否 | 5 | 用于辅助判断的样本行数上限 |

## Outputs

返回 `Dict[str, Any]`：

| 字段 | 类型 | 说明 |
|------|------|------|
| mode | str | `standard_qa` / `mapped_qa` / `unstructured_excel` |
| mapping | Optional[Dict[str,int]] | `map_excel_columns` 结果，canonical_name -> 0-based 列索引；无法映射为 None |
| reason | str | 判定原因（人类可读） |
| confidence | float | 0~1 置信度 |
| headers | List[Any] | 识别到的表头 |
| sheet_name | Optional[str] | 命中的 sheet 名 |
| sample_rows | List[List[Any]] | 样本行（最多 sample_row_limit 行） |

## 判定规则（优先级从上到下）

1. 文件无法读取 / 无表头 sheet → `unstructured_excel`，confidence 0.3（安全降级，不抛错）。
2. 表头（归一化小写）命中标准字段对：`title+content` 或 `question+answer` → `standard_qa`，confidence 0.95。
3. `map_excel_columns(headers)` 能解析出 title+content（含中文/别名）→ `mapped_qa`，confidence = min(0.9, 0.6 + 0.3*样本行 title/content 填充率)。
4. 否则 → `unstructured_excel`，confidence 0.6。

## 依赖函数

- `map_excel_columns(headers)` — 表头到 canonical 字段的映射；返回 None 表示无法解析出 title+content。
- 模块级常量 `_STANDARD_QA_HEADER_PAIRS`。

## SQL

无。

## CLI

已注册到 `src/kdb/mining/common/schema/search_records.py` 的 `fire.Fire({...})`，可经 `python src/kdb/mining/common/schema/search_records.py classify_excel_upload --excel_file=... [--sample_row_limit=5]` 调用。

## Source

`src/kdb/mining/common/schema/excel_import.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
