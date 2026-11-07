# tests/test_search_api.py

## Inputs

FastAPI `TestClient`，注入假的 KnowledgeService；不访问 Elasticsearch，不包含真实凭据。

## Outputs

验证 `/search` 与 `/web_search` 的 HTTP Basic 认证、旧字段映射、分数过滤、向量字段剔除和
分页总数契约。

## SQL

无。
