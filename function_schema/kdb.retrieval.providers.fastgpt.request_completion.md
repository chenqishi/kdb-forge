# kdb.retrieval.providers.fastgpt.request_completion

## Signature

`request_completion(url, text, api_key)`

## Inputs

原 CONFIG 的 knowledge_base_url、请求文本和原 api_key。保持 Authorization/Content-Type、stream=False、detail=True、单条 user message 与 AsyncClient 生命周期。

## Outputs

原 httpx response。状态码处理与 HTTPException 留在原 HTTP 入口；不新增重试、超时或 JSON 解析行为。

## SQL

无。

## Source

`src/kdb/retrieval/providers/fastgpt.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
