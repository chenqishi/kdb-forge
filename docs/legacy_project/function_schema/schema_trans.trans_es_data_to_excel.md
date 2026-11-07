# trans_es_data_to_excel

## 所属文件
`commons/schema_trans.py:1721`

## 功能描述
把「一行一个 JSON」的 ES 数据文件转成单 sheet xlsx。`gen_audit_data.sh` 系列脚本
和 `data_control_tools/export_qa_to_excel.py` 的 Excel 落盘都走它。

## Inputs
- `es_data_file` (str) — JSONL 路径，每行一个扁平 JSON
- `output_file` (str) — 输出 xlsx
- `headers` (None | list | tuple | str) — 列名；str 按逗号拆分；None 用默认 11 列
- `is_need_trans_column` (bool | str) — 追加「是否已经上线」列，值由 `audit_result` + `quality_level` 推出

## Outputs
无返回值，副作用是写 `output_file`。

## 取值方式
逐行 `data.get(header, '')` —— **扁平取值，不支持 `a.b` 这样的嵌套路径**。
需要嵌套字段（如 `primary_category.cate2_name`）的调用方必须自己先拍平。
唯一特例是 `synonyms_title`，按 `'|'.join(...)` 拼接。

## 2026-08-11 改动
`elif isinstance(headers, tuple)` → `elif isinstance(headers, (list, tuple))`。
原来传 `list`（最自然的类型）会掉进末尾的 `else: raise ValueError("headers参数类型错误")`。
纯新增支持，`None` / `tuple` / `str` 三种老用法行为不变。

## SQL
不涉及。

## 注意
- **逐行 `try/except ... continue`**：某一行写失败（openpyxl 的 `IllegalCharacterError`、
  超过 32767 字符的单元格）只会打一条 error 日志，**整行被静默丢掉**，返回值看不出来。
  调用方要么在上游洗数据（见 `export_qa_to_excel.clean_cell_text`），
  要么写完回读行数复核（见 `export_qa_to_excel.verify_excel_rows`）。
- 列宽自动计算，上限 100。
