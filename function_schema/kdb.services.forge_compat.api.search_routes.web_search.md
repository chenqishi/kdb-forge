# kdb.services.forge_compat.api.search_routes.web_search

## Signature

`web_search(request: WebSearchRequest, _credentials: Optional[HTTPBasicCredentials]=Depends(_require_search_auth)) -> WebSearchResponse`

## Inputs

`WebSearchRequest`: `text`、`page_size`、`page_num`、`index_names`、`client`、`need_from_history`、
`condition_dicts`、`score_threshold`。HTTP Basic 认证由路由依赖校验。

## Outputs

保持旧 `/web_search` 响应：`{"results": [...], "total_count": N, "current_count": N}`。
返回原始字段但移除 embedding 字段，`indexes` 只保留每项 `text`；由 `KnowledgeService.web_search`
执行 ES8.17 BM25 分页路径并保留 score 归一化。

## SQL

无；读取 Elasticsearch 8.17。

## Source

`src/kdb/services/forge_compat/api/search_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
