# kdb.mining.document.maintenance.repair_images.refix_task_documents

## Signature

`refix_task_documents(task_id, script_dir=None, only_files=None, mapping_name='translated_mapping.txt', output_mapping='translated_mapping_imgfixed.txt', execute=False)`

## Purpose

批量修复某个离线任务里「每页重复列出全文档图片」的解析产物：对指定文件重新解析
（使用当前已修复的 `parse_pdf_to_json`），再用 `remap_parsed_images` 贴回已有多模态结果，
输出修复版 `content_multimodal_fixed.json` 与一份新的 mapping 文件供阶段9 使用。

不覆盖原有 `content.json` / `content_multimodal.json`，原产物保持可回溯。

## Inputs

- `task_id` (str): 离线任务 id，用于定位 `data/off_task_data/<task_id>`。
- `script_dir` (str): 仓库根目录，默认当前工作目录。
- `only_files` (str|None): 可选，文本文件路径，每行一个 `file_name`；不传则处理 mapping 里全部文件。
- `mapping_name` (str): 输入 mapping 文件名，默认 `translated_mapping.txt`
  （制表符分隔，字段1=file_name，末字段=解析后的 json 路径）。
- `output_mapping` (str): 输出 mapping 文件名，默认 `translated_mapping_imgfixed.txt`。
- `execute` (bool): 默认 False 只做 dry-kdb.entrypoints.cli.generate_segments 统计，不写文件。

## Outputs

- `str`: 报告 JSON 文件路径。报告含每个文件的 旧图数/新图数/命中数/未命中数、
  文本是否逐页一致、以及是否写出修复文件。

副作用（execute=True 时）：
- 在每个文件的解析目录下写 `reparsed/` 子目录（新图片文件）与 `content_multimodal_fixed.json`
- 在任务目录写 `output_mapping`（未处理的文件沿用原路径，保证 235 篇齐全）

## SQL

No SQL access.

## 分页一致性校验（2026-09-02 修订）

写盘前校验重解析与原产物的文本是否逐页一致，不一致则跳过该文件（沿用旧解析）。

判定放宽了一处：旧解析里**零文本页**只是因为 bug 把整篇文档的图挂了上去才显得非空，
新解析该页真的没内容时会被 `parse_pdf_to_json` 的 `if content:` 丢掉——这不算分页变化。

现在的判定是三条同时成立：
1. 新解析不能凭空多出页；
2. 被丢掉的页在旧解析里必须本来就没有文字（`dropped_pages_had_text` 为空）；
3. 共有页的文本逐页完全相同。

## Source

`src/kdb/mining/document/maintenance/repair_images.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
