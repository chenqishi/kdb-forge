# KnowledgeService.render_multimodal_urls

## Inputs
检索结果文档，含 `content`、可选 `multimodal_contents`。
## Outputs
无；原地替换内部 `[multimodal_prefix]path`，有 fileName 时追加 URL 编码的 filename；外链不变。
## SQL
无。
