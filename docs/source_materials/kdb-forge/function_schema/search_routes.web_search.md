# search_routes.web_search

## Inputs

`WebSearchRequest`: `text`、`page_size`、`page_num`、`index_names`、`client`、`need_from_history`、
`condition_dicts`、`score_threshold`。HTTP Basic 认证由路由依赖校验。

## Outputs

保持旧 `/web_search` 响应：`{"results": [...], "total_count": N, "current_count": N}`。
返回原始字段但移除 embedding 字段，`indexes` 只保留每项 `text`；由 `KnowledgeService.web_search`
执行 ES8.17 BM25 分页路径并保留 score 归一化。

## SQL

无；读取 Elasticsearch 8.17。
