# kdb.retrieval.ingestion.conflict_jobs.DedupJob.analyze

## Signature

`DedupJob.analyze(self, record, additional=())`

## Inputs

见源码签名。召回/重排/主题规则/LLM，产出可审计结果、候选快照、估算与实际tokens。

## Outputs

召回/重排/主题规则/LLM，产出可审计结果、候选快照、估算与实际tokens。 错误不能算作无重复或完成。

## SQL / ES

无SQL。store通过当前ES8接口读写单一index；新增similarity_info(json list)与dedup_check(object)，不修改原审核语义。只有显式apply策略才能修改知识正文或del_flag。

## Source

`src/kdb/retrieval/ingestion/conflict_jobs.py`

## Current behavior

单index增量，Top60，阈值默认0.1、共享词默认1；三策略；内容变化/部分失败可重检。未入库先写离线标记，insert_new时先确认插入；正文变更重建向量及待审，重写多模态正文需人工核实。
