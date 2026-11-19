# kdb.retrieval.ingestion.conflict_models.rerank_candidates

## Signature

`rerank_candidates(current, candidates, *, endpoint, api_key, model='gte-rerank-v2', usage=None, timeout=60, max_input_bytes=3500, max_request_bytes=28000)`

## Inputs

当前知识、同一 index 的同类型候选、显式重排 API 地址、API key、模型名和可选 usage 字典。默认模型 gte-rerank-v2。

## Outputs

按原候选顺序返回每项相关性分数；缺失、重复或非法结果抛出异常。usage 汇总返回的 total_tokens，未返回则标记未知。API 地址和凭据不写入日志。

## SQL

无；调用重排 HTTP API。

## Current behavior

显式gte重排/直接LLM；长文本按UTF8字节保守分块，累计实测usage。不能把重排分数当重复概率；政策条件不全不得自动覆盖。

## Source

`src/kdb/retrieval/ingestion/conflict_models.py`
