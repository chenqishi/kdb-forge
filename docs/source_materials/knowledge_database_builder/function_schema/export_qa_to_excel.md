# export_qa_to_excel

## 所属文件
`data_control_tools/export_qa_to_excel.py`

## 功能描述
按来源类型导出「有效 QA」到单 sheet Excel 的只读脚本。
默认口径：`from_type_norm ∈ {document, html, manual}`（文档 / 网页 / 免审录入）、
`data_type=qa`、`audit_result >= 1`、`del_flag=0`。

流程：`EsHttpClient.iter_search_after` 拉取 → `flatten_doc` 拍平成扁平行 → 写 JSONL →
复用 `commons.schema_trans.trans_es_data_to_excel` 出 xlsx → 两道行数对账。

## 为什么不复用 control_script/gen_audit_data.sh
1. `gen_audit_data`（`knowledge_interface_tools/search_index_data_interface.py:1206`）走 `scroll_search`，
   目标索引在阿里云 ES Serverless 上，**不支持 scroll**。
2. `gen_audit_data` 没有 `from_type_norm` 过滤，且 dump 的 `_source` 带 embedding，产物 100MB+。
3. `trans_es_data_to_excel` 是扁平 `data.get(header)`，取不到嵌套的 `primary_category.*`。

本脚本只接管「查 ES + 拍平」，Excel 落盘仍是原来那个函数。

## 输出表头
```
_id | index_name | dataset | data_type | from_type_norm | from_file_name | category_path | title | content | audit_result | quality_level | insert_time
```
`data_type` 是 ES 原值（`qa` / `segment`），不做中文映射。
`--columns` 可按需裁剪 xlsx 的列（按传入顺序），**JSONL 始终落全量字段**。
`title` = 问题，`content` = 答案（沿用 `gen_audit_data` 的列名）。
`from_type_norm` 列写的是**中文标签**，不是 ES 原值。
`category_path` 是类目**全路径**（`一级-二级`），没有类目的落到默认类目。

## 函数

### `extract_from_file_name(source) -> str`
来源文件/网页：网页类是原文 URL，文档类是文件名，免审录入 / 早期导入是 Excel 表名。
存在 **`ext_info.from_file_name`** 里，不是顶层字段（按条件查 ES 时要映射成
`ext_info.from_file_name.keyword`，见 `es_search_interface`）。取不到返回空串。
`SOURCE_FIELDS` 里只请求 `ext_info.from_file_name` 这一条路径——`ext_info` 整对象带着
`topics` / `phrases` / `tags` 几十条长数组，拉全会把流量翻几倍。

**录入时间用 `insert_time`，不要用 `update_time`**：批量重打标 / 批量改字段会把整批
`update_time` 刷成同一个时间（mercado_local 里就是 2026-07-23），那不是知识录入时间。

### `select_headers(columns) -> List[str]`
`--columns` 解析成 xlsx 表头：空 / `all` → 全量 `HEADERS`；否则按传入顺序取子集。
列名必须是 `HEADERS` 里的值，**写错直接抛 `ValueError`**——
`trans_es_data_to_excel` 对取不到的 header 是写空单元格，拼错会安静地出一整列空白。

### `normalize_data_types(data_type) -> List[str]`
`--data-type` 取值归一：`all` / 空 → `[]`（不加 data_type 过滤），`'qa,segment'` → `['qa','segment']`，
也接受 list/tuple。**知识不止 qa 一种**：文档挖掘同时产出 `data_type=segment` 的长文片段，
「导出所有知识」必须走 `all`，否则 segment 整批被 `term data_type=qa` 过滤掉。

### `build_export_query(from_type_norms, min_audit_result=1, data_type='qa', include_deleted=False) -> dict`
- Outputs：`{'bool': {'filter': [terms from_type_norm, term/terms data_type, range audit_result gte, term del_flag=0]}}`
- `data_type` 单值出 `term`，多值出 `terms`，`all` 不加该过滤。
- `min_audit_result` 用 `gte` 而不是 `terms [1,2]`：审核值口径历史上变过
  （老文档 1=通过/2=不通过，当前自动审核是 high→2），「有效」统一按 `audit_result > 0` 理解。
- `from_type_norms` 传空列表 = 不限制来源（CLI 的 `--from-type-norm all`）。

### `norm_from_type_label(from_type_norm) -> str`
`document→文档`、`html→网页`、`manual`/`manual_input→免审录入`、
`auto_learning`/`自动学习→自动学习`、`teacher_training`/`老师培训→老师培训`、`other`/`其他→其他`。
**认不出来的值原样返回**，不能返回空串——否则导出里会出现一批来源为空的行且无人察觉。

归一规则来源：`knowledge_interface_tools/knowledge_tools.py:43` `get_from_norm_type`。
仓库里没有「免审录入」这个字面量，中文标签由本函数产出。

### `extract_category(source, default_category='默认分组') -> str`
返回类目**全路径**。取值顺序：
`primary_category.category_path` → 用 `cate1_name`…`cate4_name` 按层级拼 →
`category_infos` 里 `score` 最高那条的 `category_name` → `default_category`。

`primary_category` **没有 `category_name` 子字段**（构造逻辑见
`knowledge_interface_tools/search_index_data_interface.py:609-623`），只有 `category_path`
和 `cate1_name`…`cate4_name`；`category_name` 是 `category_infos[]` 里的字段。

默认类目用「默认分组」而不是别的字面量：`category_id=1` 在类目树里就叫这个，
索引里已有的默认类目文档 `category_path` 也是它，不要凭空造一个类目树上没有的名字。
CLI 用 `--default-category` 可改。

### `clean_cell_text(value) -> value`
洗掉 `[\x00-\x08\x0b\x0c\x0e-\x1f]`，并把超过 32767 字符的文本截断。
`trans_es_data_to_excel` 是逐行 `try/except continue`，openpyxl 抛 `IllegalCharacterError`
或超长会让**整行被静默丢掉**，所以必须在拍平阶段就洗干净。

### `flatten_doc(doc_id, source, index_name) -> dict`
key 与 `HEADERS` 一一对应，所有值过 `clean_cell_text`。

### `export_rows(es, indexes, query, rows_file, page_size=1000, limit=None) -> list[dict]`
逐索引 search_after 拉取并追加写 JSONL，返回全部行。

### `reconcile(es, indexes, query, rows) -> dict`
与 ES `_count` 逐索引比对，不一致抛 `RuntimeError`。**不是可选步骤**——导出脚本最常见的失败
方式就是「少了一批却看起来跑成功了」。指定 `--limit` 时跳过。

### `verify_excel_rows(excel_file, expected) -> int`
回读 xlsx 数据行数（`max_row - 1`），与期望不符抛 `RuntimeError`。防的是上面说的静默丢行。

## SQL
不涉及 SQL（数据源是 ES 不是 MySQL）。

## ES 读写

| 索引 | 读/写 | 字段 | 说明 |
|---|---|---|---|
| `mercado` / `mercado_local` | 读 | `_id` | 导出首列 |
| | 读 | `title` / `content` | 问题 / 答案，`text` + `ik_max_word` |
| | 读 | `dataset` | `keyword` |
| | 读 | `primary_category.cate1_name`…`cate4_name` / `category_path` | 类目 |
| | 读 | `category_infos[].category_name` / `.score` | 动态字段，`primary_category` 缺失时的兜底 |
| | 读 | `quality_level` | `keyword` + lowercase normalizer |
| | 过滤/读 | `from_type_norm` | `keyword` |
| | 过滤/读 | `audit_result` | `integer` |
| | 过滤 | `data_type` | `keyword`，`qa` / `segment` |
| | 过滤 | `del_flag` | `integer`，0 有效 1 软删 |

mapping 来源：`knowledge_interface_tools/es_search_interface.py:87-198`。
**全程只读，不写 ES。**

## 注意
- `from_type_norm` 存量有中文历史写法（`其他` / `老师培训` / `自动学习` 等）。
  2026-08-11 在 mercado 两个索引上实测：这些历史写法的文档 `del_flag` 全部 = 1，
  所以在 `del_flag=0` 前提下按 `from_type_norm` 过滤与按 `from_type` 归一化过滤结果一致（差集 0 条）。
  **换索引跑之前必须重新核这一条**，否则会重蹈 `docs/payoneer_olive_quality_relabel.md` 的漏数据。
- `mercado_local` 里 `primary_category.category_path` 是 `keyword` 类型（没有 `.keyword` 子字段），
  `mercado` 里是 `text` + `.keyword`。做聚合对账时两边字段名不一样。
- main 机器上要用 `/root/miniconda3/envs/py38/bin/python`（有 openpyxl + requests）；
  `python` / `python3` / `/usr/bin/python3` 都没有 openpyxl。
