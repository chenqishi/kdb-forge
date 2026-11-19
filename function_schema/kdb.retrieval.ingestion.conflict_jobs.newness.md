# kdb.retrieval.ingestion.conflict_jobs.newness

## Signature

`newness(record)`

## Inputs

知识记录与候选列表。

## Outputs

按insert_time排序，未入库数据按本批次顺序视为新数据；同时间按ID确定稳定顺序，缺失存量时间时拒绝修改策略。

## SQL

无。

## Current behavior

单index增量，Top60，阈值默认0.1、共享词默认1；三策略；内容变化/部分失败可重检。未入库先写离线标记，insert_new时先确认插入；正文变更重建向量及待审，重写多模态正文需人工核实。

## Source

`src/kdb/retrieval/ingestion/conflict_jobs.py`
