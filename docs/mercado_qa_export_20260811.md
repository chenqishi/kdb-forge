# mercado / mercado_local 有效 QA 导出（2026-08-11）

## 需求口径

导出 `mercado` + `mercado_local` 两个索引里：

- 来源为**文档 / 网页 / 免审录入**（`from_type_norm ∈ {document, html, manual}`）
- **有效**：`audit_result > 0`
- QA 数据：`data_type = qa`
- 未软删：`del_flag = 0`（与用户确认）

字段：Q/A、`from_type_norm`（转成中文）、`dataset`、类目。单 sheet xlsx。

## 结论

**7228 条**，产物 `output/mercado_qa_export_20260811/mercado_qa_export_20260811.xlsx`
（明细 JSONL 同目录）。

| 索引 | 文档 | 网页 | 免审录入 | 小计 |
|---|---|---|---|---|
| mercado | 1383 | 810 | 370 | 2563 |
| mercado_local | 186 | 4435 | 44 | 4665 |
| 合计 | 1569 | 5245 | 414 | **7228** |

列：`_id | index_name | dataset | from_type_norm | category_path | title | content | audit_result | quality_level`
（`title` = 问题，`content` = 答案，沿用 `gen_audit_data` 的列名；
`category_path` 是类目全路径，没有类目的落「默认分组」，实测导出后无空值）

## 命令

```bash
ssh main && cd /root/knowledge_database_builder
git pull --ff-only
PYTHONPATH=. /root/miniconda3/envs/py38/bin/python data_control_tools/export_qa_to_excel.py \
    --indexes mercado,mercado_local \
    --from-type-norm document,html,manual \
    --min-audit-result 1 \
    --output-dir output/mercado_qa_export_20260811
```

`--limit N` 可先抽样。**必须用 `/root/miniconda3/envs/py38/bin/python`**（Python 3.9.0，
有 `openpyxl 3.1.5` + `requests 2.32.3`）；`python` / `python3` / `/usr/bin/python3` 都没有 openpyxl。

## 为什么没复用 control_script/gen_audit_data.sh

仓库现成的导出方法是 `gen_audit_data.sh`（`gen_audit_data` 出 JSONL →
`trans_es_data_to_excel` 出 xlsx），三点用不了：

1. `gen_audit_data` 走 `scroll_search`，而这两个索引在阿里云 **ES Serverless**
   （`config/config_es_engine.json` → `for-kuajing-bot-a4d...es-serverless.aliyuncs.com`，
   注意 `config_for_search_index.json` 里指向的是 `/root/dify/knowledge_database_builder/config/`
   下的同一份），Serverless 不支持 scroll。
2. `gen_audit_data` 没有 `from_type_norm` 过滤，`_source` 还带 embedding，历史产物单文件 100MB+。
3. `trans_es_data_to_excel` 是扁平 `data.get(header)`，取不到嵌套的 `primary_category.*`。

所以新增 `data_control_tools/export_qa_to_excel.py` 接管「查 ES + 拍平」，
xlsx 落盘仍复用 `trans_es_data_to_excel`。

## 踩到 / 避开的坑

### 1. `primary_category` 没有 `category_name` 子字段

需求里说的「primary_category 中的 category_name」在 ES 里并不存在。
`primary_category` 只有 `category_path`（`一级-二级`）和 `cate1_name`…`cate4_name`
（构造逻辑见 `knowledge_interface_tools/search_index_data_interface.py:609-623`）。
`category_name` 是 `category_infos[]` 里的字段，不是 `primary_category` 里的。

处理（与用户确认后）：**只出一列 `category_path` 全路径**。取值顺序
`category_path` → 按 `cate1_name`…`cate4_name` 拼 → `category_infos` 里 score 最高那条
→ 默认类目。实测只有 4 条 mercado 文档两处都没有（已回查 ES 确认原数据就是 `null`，
不是抽取 bug），落到默认类目。

默认类目用「**默认分组**」而不是「默认类目」：`category_id=1` 在类目树里就叫这个，
索引里已有 1415 条默认类目文档的 `category_path` 也是它，不要凭空造一个树上没有的名字。
要改用 `--default-category`。

`mercado` 的 `primary_category.category_path` 是 `text` + `.keyword`，
`mercado_local` 的是纯 `keyword` —— **两边聚合时字段名不一样**，对账脚本要注意。

### 2. 「免审录入」= `from_type_norm = manual`

仓库里搜不到「免审录入」这个字面量。依据是
`knowledge_interface_tools/knowledge_tools.py:68` 把 `from_type` 里所有
`handle*` / `manual*` 归一成 `manual`，`RAG_MANAGEMENT_API_DOC.md:47` 的手动录入示例
也是 `from_type=manual`。中文标签由导出脚本产出（`FROM_TYPE_NORM_LABELS`）。

### 3. 这次可以按 `from_type_norm` 过滤（和 payoneer_olive 那次相反）

存量数据里 `from_type_norm` 有中文历史写法。这两个索引里实测：
`其他` 539 / `老师培训` 67 / `alina修正/新增` 2 / `JW_IDS_Only` 1 / `自动学习` 1，共 610 条，
**`del_flag` 全部 = 1**。所以在 `del_flag=0` 前提下，
按 `from_type_norm ∈ {document,html,manual}` 过滤 与 按 `from_type` 归一化过滤
结果完全一致（差集实测 **0 条**）。

**换索引跑之前必须重新核这一条**，否则会重蹈
`docs/payoneer_olive_quality_relabel.md` 里「按 from_type_norm 过滤漏掉 1909 条」的坑。

### 4. `trans_es_data_to_excel` 会静默丢行（已加双保险）

它是逐行 `try/except ... continue`：openpyxl 遇到控制字符抛 `IllegalCharacterError`、
单元格超 32767 字符也抛错，**整行被丢掉且返回值看不出来**。
所以导出脚本：①拍平阶段就 `clean_cell_text` 洗控制字符 + 截断超长；
②写完 `verify_excel_rows` 回读 xlsx 行数复核；③拉取后与 ES `_count` 对账，不一致直接抛错。

顺手修了它一个类型 bug：`headers` 传 `list`（最自然的类型）原来会掉进
`else: raise ValueError("headers参数类型错误")`，只认 `tuple` / `str`。现在 `list` 也接受。

### 5. 前端页面上 mercado 显示 ~2800，和导出的 2563 不矛盾

前端那个数把「自动学习」也算进去了，不是同一个口径。
`mercado` 索引 `del_flag=0` 的实际分布（qa）：
文档 1817（audit>0 1383）/ 网页 1013（810）/ 免审录入 376（370）/
老师培训 265（262）/ 自动学习 7289（**audit>0 只有 14**，其余 7243 条待审）/ 其他 41（19）。
另有 331 条 segment。所以本次口径（三类来源 + audit>0 + 仅 qa）= 2563 是对的。

顺带确认不是索引选错了：合并索引 `mercado_all_kg`（2026-08-03 建，49077 docs，
全部 `del_flag=0`）同口径下是 7218 条，与本次 7228 基本一致。

### 6. 软删数据量很大

`mercado` 里符合来源+审核条件但 `del_flag=1` 的有 4738 条（其中网页类 4438 条），
`mercado_local` 16 条。本次按「有效」口径排除。要含进去用 `--include-deleted`。

## 校验

- 行数：脚本内置与 ES `_count` 逐索引比对，`mercado` 2563 / `mercado_local` 4665 全等。
- xlsx 回读：7228 数据行，`_id` 无重复，`title`/`content`/`dataset` 无空值。
- 分布：xlsx 按 `index_name × from_type_norm` 统计与 ES terms 聚合逐格一致。
- `audit_result` 取值只有 `2`(6761) 和 `1`(467)，无 `0` / `-1`。
- 随机 5 行回查 ES，`title`/`content`/`dataset`/`audit_result`/类目全部一致，
  且 `del_flag=0`、`data_type=qa`。
- 单测 `tests/test_export_qa_to_excel.py` 26 项通过（含 Excel 往返、控制字符、超长截断、
  对账失败抛错）；`tests/test_relabel_qa_quality.py` 26 项回归通过（EsHttpClient 搬家后）。

## 相关代码

- `data_control_tools/export_qa_to_excel.py` — 本次新增的导出脚本
- `commons/es_http_client.py` — 从 `relabel_qa_quality_by_llm.py` 抽出的裸 HTTP ES 客户端
- `function_schema/export_qa_to_excel.md`、`function_schema/es_http_client.EsHttpClient.md`、
  `function_schema/schema_trans.trans_es_data_to_excel.md`
