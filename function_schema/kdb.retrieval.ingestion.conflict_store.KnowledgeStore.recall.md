# kdb.retrieval.ingestion.conflict_store.KnowledgeStore.recall

## Signature

`KnowledgeStore.recall(self, record, limit=60)`

## Inputs

见源码签名。复用在线search_data，混合文本/embedding TopN不按分数、platform或审核过滤；类型严格隔离。

## Outputs

复用在线search_data，混合文本/embedding TopN不按分数、platform或审核过滤；类型严格隔离。 错误不能算作无重复或完成。

## SQL / ES

无SQL。store通过当前ES8接口读写单一index；新增similarity_info(json list)与dedup_check(object)，不修改原审核语义。只有显式apply策略才能修改知识正文或del_flag。

## Source

`src/kdb/retrieval/ingestion/conflict_store.py`

## Current behavior

同index ES8边界，候选不限platform/审核，目标可筛audit_result=-1/时间/task_id/未完成。修改先journal，再核对内容/审核及CAS版本；非NotFound读取失败不可隐藏。
