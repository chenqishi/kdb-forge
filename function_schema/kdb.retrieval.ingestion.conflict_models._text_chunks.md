# kdb.retrieval.ingestion.conflict_models._text_chunks

## Signature

`_text_chunks(text, max_bytes)`

## Inputs

显式模型配置、文本及usage累计器。

## Outputs

按UTF8字节上界切分文本，避免超过重排模型单项token限制；保留所有字符。

## SQL

无。

## Current behavior

显式gte重排/直接LLM；长文本按UTF8字节保守分块，累计实测usage。不能把重排分数当重复概率；政策条件不全不得自动覆盖。

## Source

`src/kdb/retrieval/ingestion/conflict_models.py`
