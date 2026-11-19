# kdb.retrieval.ingestion.conflict_store.KnowledgeStore.patch

## Signature

`KnowledgeStore.patch(self, expected, fields)`

## Inputs

见源码签名。核验当前内容快照，journal写入前镜像后CAS局部更新；任何失败显式传播。

## Outputs

核验当前内容快照，journal写入前镜像后CAS局部更新；任何失败显式传播。 错误不能算作无重复或完成。

## SQL / ES

无SQL。store通过当前ES8接口读写单一index；新增similarity_info(json list)与dedup_check(object)，不修改原审核语义。只有显式apply策略才能修改知识正文或del_flag。

## Source

`src/kdb/retrieval/ingestion/conflict_store.py`

## Current behavior

同index ES8边界，候选不限platform/审核，目标可筛audit_result=-1/时间/task_id/未完成。修改先journal，再核对内容/审核及CAS版本；非NotFound读取失败不可隐藏。
