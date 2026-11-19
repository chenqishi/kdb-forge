# kdb.retrieval.ingestion.conflict_check.topic_terms

## Signature

`topic_terms(record, aliases=None)`

## Inputs

见源码签名。提取显式keywords及jieba主题词，过滤常见虚词，支持词汇别名。

## Outputs

提取显式keywords及jieba主题词，过滤常见虚词，支持词汇别名。 错误不能算作无重复或完成。

## SQL / ES

无SQL。store通过当前ES8接口读写单一index；新增similarity_info(json list)与dedup_check(object)，不修改原审核语义。只有显式apply策略才能修改知识正文或del_flag。

## Source

`src/kdb/retrieval/ingestion/conflict_check.py`

## Current behavior

同类型候选比较；重排0..1分数与主题规则；duplicate/overlap/conflict/different/uncertain，证据须在两侧原文逐字找到。政策冲突须确认共同生效版本/时段，否则uncertain。different仅计入evaluated_ids，不写关系；模型错误显式failed。
