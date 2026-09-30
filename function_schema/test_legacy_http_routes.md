# tests/test_legacy_http_routes.py

## Inputs

FastAPI TestClient，注入 fake KnowledgeService 与 fake modifier；不连接 Elasticsearch，不写生产数据。

## Outputs

验证 11 个旧 HTTP 路径的挂载、请求映射、响应模型、参数错误和 Dify modifier 能力开关。

## SQL

无。
