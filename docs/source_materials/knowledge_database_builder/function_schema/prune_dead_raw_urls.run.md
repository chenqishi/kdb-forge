# run

## 所属文件
`data_control_tools/prune_dead_raw_urls.py`

## 功能描述
删掉知识里那些**指向不存在对象**的裸图片 URL。默认 dry-run。

与 `prune_page_mismatched_images.py` **正交**：那个处理 `[multimodal_prefix]<path>` 标记（图挂错页），
本工具处理**裸 URL 文本**——它躺在 `multimodal_contents` 的 **text 项**文字里，
拼接时当普通正文接上，从来不是 image 项，按标记处理的工具碰不到它。

## Inputs
- `config_path` (str, 默认 `config/config_es_engine.json`)
- `index` (str)
- `work_dir` (str) — plan / rollback 落盘目录
- `embedding_config` (str, 默认 `config/config_ali_embedding.json`)
  —— DashScope key 在这个文件里，用 `config_for_search_index.json` 会 401
- `task_ids` (Sequence[str], 可选) — 默认全库
- `bulk_batch` (int, 默认 **50**) — 故意比通用默认 200 小：Serverless 单请求 15MB 上限，
  partial update 也带 1024 维向量
- `execute` (bool, 默认 False)

## Outputs
`Dict` — `{stats, plan_file, dead_urls, probed_urls, [dry_run], [updated], [failed], [rollback_file], [row_errors]}`

`stats` 里的 action：
- `prune` — 自动处理
- `review_empty` / `review_no_text` / `review_dangling_colon` — 不自动改，交人工
- `跳过_content非拼接产物` — 自检没通过，不赌

## 修法：改 multimodal_contents 后重拼 content，不做字符串手术
入库时 `content = SearchDataInterface.join_multimodal_contents(multimodal_contents)`。
所以本工具只改 text 项里的文字，再用同一套规则重拼 content，
这样 content 与结构化字段天然一致，不会出现「标记数≠图数」。

**重拼前必须自检**（`rebuild_matches_current`）：拿**未修改**的 `multimodal_contents`
重拼一遍，能逐字复现现有 content 才可以用。复现不了说明这条 content 不是纯拼接产物，跳过交人工。

## 判据只有一个：实际发 HEAD 请求
特征式判据全部不可用：
- 「有没有 `?filename=` 后缀」—— 库里存的全是裸 URL，后缀是检索服务返回时才拼的
- 「hash 长得像不像」—— 抄错一位和正常 hash 形态上没区别

## 金丝雀自检（硬性）
被测集合里必须包含已知坏样本 `CANARY`，否则直接抛错拒绝继续。
**栽过一次**：被测集合只收集了标记路径 + `multimodal_contents[].path`，
把裸 URL 整类漏掉，于是「1579 个对象非 200 = 0」这个结论自洽地骗了人。

## 提取必须按 `https://` 边界非贪婪切分
正文里多个 URL **无分隔符直接粘在一起**（`….pnghttps://file.marsmind.cc/…`）。
贪婪正则跨过边界把拼接串当一个 URL 测，必然 404。
**栽过一次**：错切出 184 个串、报 171 个死链；正确切分后是 1015 个 URL、32 个死链（3.2%）。

## SQL / ES schema
读：`del_flag` / `task_id` / `content` / `multimodal_contents` / `title` / `data_type` / `audit_result`

写（`_bulk` partial update，只动这三个字段）：
- `content` — 由 `join_multimodal_contents` 重拼
- `multimodal_contents` — 只改 text 项文字，image 项原样
- `content_embedding` — 必须重算

**不动**：`indexes`（不重算那几千条索引 embedding）、`title`、mapping、不 reindex。
不用 `update_by_query`——它会把整条 `_source`（含向量）重新索引，代价大得多。

## 测试
`tests/test_prune_dead_raw_urls.py`（21 项）
