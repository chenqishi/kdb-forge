# kdb.retrieval.ingestion.conflict_jobs.DedupJob.__init__

## Signature

`DedupJob.__init__(self, store, models, *, limit=60, threshold=0.1, min_shared_topics=1, aliases=None)`

## Inputs

见源码签名。单index store、模型gateway及策略参数；默认record_only、Top60。

## Outputs

单index store、模型gateway及策略参数；默认record_only、Top60。 错误不能算作无重复或完成。

## SQL / ES

无SQL。store通过当前ES8接口读写单一index；新增similarity_info(json list)与dedup_check(object)，不修改原审核语义。只有显式apply策略才能修改知识正文或del_flag。

## Source

`src/kdb/retrieval/ingestion/conflict_jobs.py`

## Current behavior

单index增量，Top60，阈值默认0.1、共享词默认1；三策略；内容变化/部分失败可重检。未入库先写离线标记，insert_new时先确认插入；正文变更重建向量及待审，重写多模态正文需人工核实。
