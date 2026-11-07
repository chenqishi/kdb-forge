# kdb.integrations.data_control.prune_page_mismatched_images.run

## Signature

`run(config_path: str, index: str, task_id: str, work_dir: str, embedding_config: str='config/config_ali_embedding.json', window: int=DEFAULT_WINDOW, execute: bool=False, bulk_batch: int=DEFAULT_BULK_BATCH, only_duplicate: bool=False, attach_when_no_text: bool=False, only_ids: Optional[Sequence[str]]=None) -> Dict[str, Any]`

## Inputs

Existing function signature and business inputs are unchanged. Read together with the pre-existing function contract indexed by its original source prefix.

- `config_path` (str, 默认 `config/config_es_engine.json`)
- `index` (str)
- `task_id` (str)
- `work_dir` (str) — plan.json / rollback.jsonl 落盘目录
- `embedding_config` (str, 默认 `config/config_ali_embedding.json`)
  —— **注意**：DashScope key 在 `config_ali_embedding.json`，
  不在 `config_for_search_index.json`（用后者会 401）
- `window` (int, 默认 60)
- `execute` (bool, 默认 False)
- `attach_when_no_text` (bool, 默认 False) — 正文除图片标记外**没有一个字**时
  （这种 QA 的「答案」本来就是图，标题常是「…的图片链接是什么」），
  若该页有上传过的正确图就补挂，而不是当成 `skipped_empty_text` 跳过。
  现挂的是折扣活动界面（错图），该页正确图 OCR 是「Invalid Price Error(s)…Validation Errors」，完全对口。
- `only_ids` (Sequence[str], 可选) — 只处理这些 `_id`，用于精准修单条、不动同任务其余行
- `only_duplicate` (bool, 默认 False) — **只裁同内容重复图，不按页码区间裁**。
  用于已经走过「重跑生成」修复的批次（如 `74256b78`）：它的图是新管线按页分配的，
  其中 168 张全部是「距离本页码区间 1 页」且全是 segment，只有 5 张是真重复。
- `bulk_batch` (int, 默认 200)

## Outputs

Only dependency imports and canonical project/source/resource locations change. Runtime interfaces, business request parameters, output data, error/exit behavior and initialization timing remain those of the existing implementation. Service task launch and optional LLM plugin details are defined in off_task_app.* and local_llm_adapter.* contracts.

`Dict` — `{stats, plan_file, rows_to_change, [dry_run], [updated], [failed], [rollback_file], [left_for_review]}`

## SQL

No query, field, table, scoring or data mutation change. No backend or subprocess was kdb.mining.generation.run during migration validation.

## Description

主流程：建等价类与页→图索引 → 逐条算方案 → 落 plan.json → （`--execute`）写回 ES。默认 dry-kdb.mining.generation.run。

## 补挂候选的页码区间为什么会放宽一页

`prune_and_attach` 取候选时，先严格按本行页码区间；取不到才放宽到 ±1 页。
段落常在页末断开，「如下图所示」指的图落到了下一页
第 1 页真图 0 张，话术指的图在第 2 页）。

**放宽只作用于补挂这一档，批量裁剪仍按严格区间。** 依据是随机基线检验：
±1 页带内被裁 383 张占非 duplicate 被裁量的 17.4%，
而「从整篇图池随机挑」的期望是 14.1%（实际/期望 1.24，接近巧合），
且这 383 张里只有 1 张有话术指着。无脑放宽会把巧合命中的错图当成对的留下来。

## 前置条件

任务目录下必须已有（先跑 `refix_doc_images.py kdb.mining.generation.run --task_id=X --execute=True`）：
- `translated_mapping_imgfixed.txt` — 列 [1] from_file_name，列 [4] 解析目录
- `multimodal_data_info.json` — 建 `s3_path -> md5` 等价类，需要本地图片文件还在

## SQL / ES schema

读：`del_flag` / `task_id` / `data_type` / `content` / `multimodal_contents` / `ext_info` / `title`

写（`_bulk` partial update，只动这三个字段）：
- `content` — 去掉被裁的 `[multimodal_prefix]<path>` 标记，正文文字不动；
  `prune_and_attach` 的行在末尾追加补挂图的标记
- `multimodal_contents` — 文本项原样保留在前，图片项按保留顺序重建
- `content_embedding` — **必须重算**，因为 content 变了

`action=review_deictic` 的行**不写回**，计入 `left_for_review`。

另有两类也不自动写：
- **裁完正文为空**（`skipped_empty_text`）：有些 QA 的答案正文**本来就只有图片、没有一个字**，
  裁掉错图后 content 变成空串，DashScope embedding 对空输入**返回 400**。
- **无文字只剩图片标记**（`image_only_rows`）：仍会写回（原来也是这个形态），但报出来。

**单行出错只跳过这一行**（`row_errors`），不中断整批 ——
第一次跑 508b09ae 就是被上面那个 400 打死，271 行一条都没写进去。
写回前每行的原 `content` / `multimodal_contents` 落 `rollback_<task>.jsonl`。

## 复核

ES 写回有可见性延迟，refresh 后立刻查会读到矛盾数字，必须隔一轮再对账。

## 测试

`tests/test_prune_page_mismatched_images.py`（纯逻辑 26 项）

## Source

`src/kdb/integrations/data_control/prune_page_mismatched_images.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
