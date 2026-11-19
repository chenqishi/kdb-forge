# kdb.retrieval.ingestion.conflict_models.ModelGateway.names

## Signature

`ModelGateway.names(self, current, candidate)`

## Inputs

见源码签名。LLM判断文件主体名称相同，版本/日期差异不改变主体。

## Outputs

LLM判断文件主体名称相同，版本/日期差异不改变主体。 错误不能算作无重复或完成。

## SQL / ES

无SQL。store通过当前ES8接口读写单一index；新增similarity_info(json list)与dedup_check(object)，不修改原审核语义。只有显式apply策略才能修改知识正文或del_flag。

## Source

`src/kdb/retrieval/ingestion/conflict_models.py`

## Current behavior

显式gte重排/直接LLM；长文本按UTF8字节保守分块，累计实测usage。不能把重排分数当重复概率；政策条件不全不得自动覆盖。
