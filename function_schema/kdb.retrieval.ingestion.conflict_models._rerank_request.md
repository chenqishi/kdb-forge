# kdb.retrieval.ingestion.conflict_models._rerank_request

## Signature

`_rerank_request(query, documents, *, endpoint, api_key, model, usage, timeout)`

## Inputs

显式模型配置、文本及usage累计器。

## Outputs

请求gte兼容API，校验每个index和0..1分数，统计成功/失败实际用量。

## SQL

无。

## Current behavior

显式gte重排/直接LLM；长文本按UTF8字节保守分块，累计实测usage。不能把重排分数当重复概率；政策条件不全不得自动覆盖。

## Source

`src/kdb/retrieval/ingestion/conflict_models.py`
