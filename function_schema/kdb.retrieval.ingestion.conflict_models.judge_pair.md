# kdb.retrieval.ingestion.conflict_models.judge_pair

## Signature

`judge_pair(current, candidate, *, request_llm, usage=None, model_name=None)`

## Inputs

两条知识、兼容 request_knowledge_llm 的模型函数、可选用量字典和模型名。

## Outputs

解析关系、理由和新旧原文证据的 JSON；空结果、非法 JSON 抛出异常。调用方继续验证证据属于原文。

## SQL

无；调用方提供模型函数。

## Current behavior

显式gte重排/直接LLM；长文本按UTF8字节保守分块，累计实测usage。不能把重排分数当重复概率；政策条件不全不得自动覆盖。

## Source

`src/kdb/retrieval/ingestion/conflict_models.py`
