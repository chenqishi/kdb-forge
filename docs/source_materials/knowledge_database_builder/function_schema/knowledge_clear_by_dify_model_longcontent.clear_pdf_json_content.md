# knowledge_clear_by_dify_model_longcontent.clear_pdf_json_content

## 描述
读取单个 PDF/DOCX 解析 JSON，通过 Dify 分段与 QA 抽取生成 QA 列表并写入输出文件。长文档先按页边界硬分段，再让 Dify 在硬窗口内做语义分段，避免超过 Dify `paragraph` 限制。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| pdf_json_file | str | 是 | 输入 JSON 文件路径 |
| output_file | str | 是 | QA JSON 输出路径 |
| dify_segment | KnowledgeCleaner-like | 是 | 分段 Dify 请求对象，需提供 `request_dify(paragraph)` |
| dify_subtract | KnowledgeCleaner-like | 是 | QA 抽取 Dify 请求对象，需提供 `request_dify(paragraph)` |
| from_file_name | str | 是 | 写入 QA 的来源文件名 |
| use_image_content | int | 否 | QA 抽取是否使用有效图片 URL，默认 0 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | QA 列表，每项包含 `q`、`a`、`from_file_name`、`from_page` |
| file | `output_file` 写入同一 QA 列表 JSON |

## 行为
- 文档整体内容小于 2000 字符时，直接调用 QA 抽取模型。
- 长文档先调用 `build_page_chunks` 生成默认不超过 80000 字符且不超过 40 页的硬窗口。
- 每个硬窗口单独调用 Dify 分段；Dify 无有效分段时使用 `fallback_page_segments` 按 10 页兜底。
- QA 抽取前调用 `split_segment_for_qa`，默认进一步限制为 30000 字符且不超过 10 页。
- 分段时不使用图片内容；QA 抽取是否使用图片 URL 由 `use_image_content` 控制，且 `add_image_context=0`。

## SQL
不读写数据库。
