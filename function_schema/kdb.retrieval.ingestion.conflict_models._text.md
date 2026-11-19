# kdb.retrieval.ingestion.conflict_models._text

## Signature

`_text(record)`

## Inputs

见源码签名。拼接知识标题/正文。

## Outputs

拼接知识标题/正文。 错误不能算作无重复或完成。

## SQL / ES

无SQL。store通过当前ES8接口读写单一index；新增similarity_info(json list)与dedup_check(object)，不修改原审核语义。只有显式apply策略才能修改知识正文或del_flag。

## Source

`src/kdb/retrieval/ingestion/conflict_models.py`

## Current behavior

显式gte重排/直接LLM；长文本按UTF8字节保守分块，累计实测usage。不能把重排分数当重复概率；政策条件不全不得自动覆盖。
