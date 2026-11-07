# mercado / mercado_local 全部知识导出（2026-09-13）

## 需求口径

导出 `mercado` + `mercado_local` 两个索引里**所有知识**（不限来源、不限 data_type），
只要 `audit_result > 0`。字段至少含 `title` / `content` / `data_type` / `from_type_norm`。
产物放 main 机器（本机磁盘不够）。

补充的两条判断（未特别指定，按既有口径取）：

- `del_flag = 0`：只导有效知识。软删的量很大（`mercado` 6482 条、`mercado_local` 17 条
  同样是 `audit_result>0`），要连软删一起导用 `--include-deleted`。
- 列沿用既有导出表头再补 `data_type`，不删旧列。

## 结论

**13344 条**，产物在 main：

```
/root/knowledge_database_builder/output/mercado_all_knowledge_20260913/
    mercado_all_knowledge_20260913.xlsx        6.0M
    mercado_all_knowledge_20260913_rows.jsonl   16M
```

xlsx 列（用户口径：不要 `index_name` / `quality_level`）：
`_id | dataset | data_type | from_type_norm | category_path | title | content | audit_result`

JSONL 仍是全量字段（含 `index_name`、`quality_level`），要加列直接改 `--columns` 重跑即可。

注意：`dataset` **不等于**索引名 —— xlsx 里 `dataset=mercado` 8548 条、`mercado_local` 4795 条、
字符串 `"null"` 1 条，而按索引是 `mercado` 3337 / `mercado_local` 10007。
去掉 `index_name` 后无法再从 xlsx 区分知识来自哪个索引，需要就从 JSONL 取。

| 索引 | qa | segment | 无 data_type | 小计 |
|---|---|---|---|---|
| mercado | 2858 | 328 | 151 | 3337 |
| mercado_local | 8116 | 1891 | 0 | 10007 |
| 合计 | 10974 | 2219 | 151 | **13344** |

按来源（`from_type_norm`）：`mercado` 文档 1474 / 网页 1035 / 免审录入 382 /
老师培训 262 / 其他 170 / 自动学习 14；`mercado_local` 网页 9750 / 文档 194 / 免审录入 63。

## 命令

```bash
ssh main && cd /root/knowledge_database_builder
git pull --ff-only
PYTHONPATH=. /root/miniconda3/envs/py38/bin/python data_control_tools/export_qa_to_excel.py \
    --indexes mercado,mercado_local \
    --from-type-norm all --data-type all \
    --min-audit-result 1 \
    --page-size 500 \
    --columns _id,dataset,data_type,from_type_norm,category_path,title,content,audit_result \
    --output-dir output/mercado_all_knowledge_20260913
```

必须用 `/root/miniconda3/envs/py38/bin/python`（只有它有 openpyxl），
其它 python 都跑不起来。

## 这次踩到的两个坑

### 1. `--data-type` 原来写死 `term data_type=qa`，segment 整批漏掉

「所有知识」不等于「所有 QA」：文档挖掘同时产出 `data_type=segment` 的长文片段
（这两个索引里 2219 条）。脚本现在支持 `--data-type all` / `qa,segment`，
并把 `data_type` 出成一列。

另有 **151 条 `mercado` 老数据根本没有 `data_type` 字段**（全是 `from_type_norm=other`，
内容是正常 QA），`all`（不加过滤）才捞得到，写 `data_type=qa,segment` 一样会漏。
xlsx 里这列为空是原数据如此，不是导出丢字段。

### 2. ES Serverless 会取消慢分片，导出静默少几千条（已在客户端修掉）

第一次跑 `mercado_local` 只导出 6675 / 10007，再跑一次是 8661 —— 每次都不一样。
原因：阿里云 ES Serverless 把跑得慢的分片任务直接取消，响应仍是 HTTP 200：

```json
{"_shards": {"total": 3, "successful": 2, "failed": 1,
             "failures": [{"shard": 0, "reason": {"type": "task_cancelled_exception"}}]}}
```

`search_after` 的游标取的是「最后一条 hit 的 sort」，而这一页少了一整个分片的数据，
游标照样前移 —— 被取消分片在这一段里的文档就**永远捞不到了**。

修复在 `commons/es_http_client.py`：`search` / `count` 默认校验 `_shards`
（外加 `timed_out`），不全就**重试整页**（游标不动，所以不会跳文档），
连续失败把页大小折半（下限 50），到底还失败抛 `PartialShardFailure`。
`count` 也要查 —— 它偏小的话导出对账会「自洽地」通过。

**这条对所有走 `EsHttpClient` 的脚本都成立**，不只是导出：聚合盘点、按条件重打标、
批量软删，只要吃了部分结果就是静默少处理一批。回归见
`tests/test_es_http_client_shards.py`。

## 校验

- 行数：脚本内置与 ES `_count` 逐索引比对，`mercado` 3337 / `mercado_local` 10007 全等。
- xlsx 回读：13344 数据行，`_id` 无重复；`content`、`from_type_norm` 无空值；
  裁列后表头 8 列与 `--columns` 一致。
- 分布：xlsx 的 `index × data_type` 与 ES terms 聚合逐格一致。
- 随机 3 行回查 ES：`title` / `data_type` 一致，且 `audit_result>0`、`del_flag=0`。
- `title` 空 2249 条 = 2219 条 segment（本来就没标题）+ 30 条 `mercado` 老师培训 QA
  （原数据就缺 `title`，是存量脏数据，本次未改）。
- 单测：`tests/test_export_qa_to_excel.py` 28 项、`tests/test_es_http_client_shards.py` 10 项通过。

## 相关代码

- `data_control_tools/export_qa_to_excel.py` — 导出脚本（`--data-type all` 本次新增）
- `commons/es_http_client.py` — 分片失败校验与整页重试
- 上一次同索引的 QA 导出口径见 `docs/mercado_qa_export_20260811.md`

---

## 2026-09-20 重导：补「来源链接」「录入时间」两列

用户要给客户发，追加两个字段：文档/网页链接 `ext_info.from_file_name`、
知识录入时间 `insert_time`。这两个字段原来不在 `SOURCE_FIELDS` 里，
**必须重新拉 ES**（不是改列，改列的话拿 JSONL 重出 xlsx 就够了）。

产物：`/root/knowledge_database_builder/output/mercado_all_knowledge_20260920/`
（xlsx 6.5M / JSONL 18M），**13745 条**，xlsx 10 列：

```
_id | dataset | data_type | from_type_norm | from_file_name | category_path | title | content | audit_result | insert_time
```

```bash
PYTHONPATH=. /root/miniconda3/envs/py38/bin/python data_control_tools/export_qa_to_excel.py \
    --indexes mercado,mercado_local --from-type-norm all --data-type all \
    --min-audit-result 1 --page-size 500 \
    --columns _id,dataset,data_type,from_type_norm,from_file_name,category_path,title,content,audit_result,insert_time \
    --output-dir output/mercado_all_knowledge_20260920
```

### 与 9-13 那版的差异（13344 → 13745）

一周内新增的真实数据，不是口径变化：`mercado` 3337 → 3739（文档类 QA +396、
segment +5、免审录入 +1），`mercado_local` 10007 → 10006（-1）。两边都与 ES `_count` 对账相等。

### 录入时间为什么是 `insert_time` 不是 `update_time`

`update_time` 会被批量重打标 / 批量改字段整批刷成同一个时间
（`mercado_local` 的网页知识全是 `2026-07-23 22:52:19`），那不是知识录入时间。
`insert_time` 两个索引 **0 缺失**，范围 `2025-02-11` ~ 导出当天。

### `from_file_name` 的值形态（发客户前要知道）

- 网页类 = 原文 URL（10784 条，占 78%）
- 文档类 = 文件名（`Emissor NF-E _ User Guide.docx`、`商家操作手册指南 (1).pdf` …）
- 免审录入 / 早期导入 = Excel 表名（`qa_mp_4_0318.xlsx_sheet1` …）
- 空值 350 条：老师培训 262 / 免审录入 83 / 自动学习 4 / 其他 1

**坑：文档类里 1078 / 2069 条的文件名是 `<32位md5>.md`**，是公众号文章转 md 后
以哈希命名上传的（内容里有 `mmbiz.qpic.cn` 图片），任务产物
`data/off_task_data/<task_id>/file_mapping.txt` 只记了「哈希名 → 本地路径」，
**没有留原始文章标题/URL**，所以这批拿不到可读来源。要给客户可读来源得另找
公众号文章清单回填，本次未做。

### 2026-09-20 追加：缺 `data_type` 的 231 条历史遗留已软删

那 151 条没有 `data_type` 的老数据（发客户时会多出一列空值），查清是
**2025-03-22 ~ 2025-04-14 那批 Excel 人工反馈回灌**：`from_type=unknown`、
`platform=Mercado`、`quality_level=mid`，来源表 `audit_data_excel_mercado_timing_v1_*_Sheet`
和 `alina3.20反馈_*_Sheet`，内容形态就是正常 QA。只有 `mercado` 有，`mercado_local` 一条没有。
当时那条入库路径没写 `data_type` 字段（不是写了空值，是字段不存在）；
现在的路径不会再产生：Excel 导入在 `commons/schema_trans.py:1736-1740` 按有没有 title
回填 `qa`/`segment`，`search_index_data_interface.py:271` 还有默认值兜底。

经确认全批软删（231 条 = 151 条 `audit_result=1` + 80 条 `audit_result=0`，
全部原本 `del_flag=0`、无 flag）：

```bash
# 1) 先落 _id 快照（must_not exists data_type + del_flag=0），拉到的条数与 _count 断言相等
# 2) 复用既有软删脚本，注意子命令是 run（不是 retire）
PYTHONPATH=. /root/miniconda3/envs/py38/bin/python data_control_tools/retire_superseded_knowledge.py run \
    --index mercado \
    --snapshot_file output/mercado_softdel_missing_data_type_20260920/snapshot_ids.json \
    --flag softdel_missing_data_type_20260920 \
    --work_dir output/mercado_softdel_missing_data_type_20260920 --execute
```

`updated=231 failed=0`；回滚文件 `output/mercado_softdel_missing_data_type_20260920/rollback.jsonl`
（要撤销用同脚本 `rollback` 子命令）。

复核照例两轮：**第一轮读到的全是旧值**（仍 live 231、打上 flag 的 0），20 秒后第二轮
才是 live 缺 data_type **0** 条、快照 231 条全部 `del_flag=1` 且带本批 flag、
`mercado` 有效知识 3739 → **3588**（-151，另外 80 条本来就 `audit_result=0` 不在口径内）。

### 最终产物（发客户用这一版）

`output/mercado_all_knowledge_20260920/`，**13594 条**（qa 11370 / segment 2224，
`data_type` 已无空值），与 ES `_count` 对账相等：`mercado` 3588 + `mercado_local` 10006。
来源分布：网页 10784 / 文档 2069 / 免审录入 446 / 老师培训 262 / 其他 19 / 自动学习 14。
