# kdb.mining.common.generation.long_qa.split_segment_for_qa

## Signature

`split_segment_for_qa(data_json, segment, max_chars=QA_MAX_CHARS, max_pages=QA_MAX_PAGES, use_image_content=0, image_placeholder_map=None)`

## Description

在 QA 抽取前再次按页边界限制语义段落长度，避免 Dify QA 抽取模型收到过长段落。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| data_json | dict | 是 | PDF/DOCX 解析后的页内容字典 |
| segment | dict | 是 | 待抽取 QA 的段落，格式包含 `pages: [start_page, end_page]` |
| max_chars | int | 否 | 单个 QA 抽取窗口最大字符数，默认 30000 |
| max_pages | int | 否 | 单个 QA 抽取窗口最大页数，默认 10 |
| use_image_content | int | 否 | 是否把有效图片 URL 纳入 QA 抽取内容，默认 0 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | QA 抽取窗口列表，格式 `{"title": str, "pages": [start_page, end_page]}` |

## 行为约束

- 使用 `merge_segment_content(..., need_add_page_num=False, add_image_context=0)` 计算 QA 输入长度。
- 不拆单页；若单页超过 `max_chars`，记录 warning 并保留为单页窗口。
- 保留原 segment title，便于日志追踪。

## SQL

不读写数据库。

## Source

`src/kdb/mining/common/generation/long_qa.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
