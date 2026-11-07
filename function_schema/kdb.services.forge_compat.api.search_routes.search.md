# kdb.services.forge_compat.api.search_routes.search

## Signature

`search(request: SearchRequest, _credentials: Optional[HTTPBasicCredentials]=Depends(_require_search_auth)) -> SearchResponse`

## Inputs

`SearchRequest`: `text`（非空）、`top_k`、`score_threshold`、`index_names`、`condition_dicts`、
`search_type`、`data_type`、`use_synonyms`。HTTP Basic 认证由路由依赖校验，凭据只从进程环境读取。

## Outputs

保持旧 `/search` 响应：`{"results": [...]}`。每条结果包含 `id`、`dataset`、时间字段、`q`、`a`、
`content`、`ext_info`、`score`、`synonyms_title`、`metadata` 和可选 `primary_category`。
检索由 `KnowledgeService.search_text` 执行，使用 ES8.17 native BM25/vector 双路，不调用 ES7 或
`script_score`。

## SQL

无；读取 Elasticsearch 8.17。

## Source

`src/kdb/services/forge_compat/api/search_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
