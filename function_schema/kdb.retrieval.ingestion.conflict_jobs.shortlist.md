# kdb.retrieval.ingestion.conflict_jobs.shortlist

## Signature

`shortlist(record, online, additional, limit)`

## Inputs

知识记录与候选列表。

## Outputs

合并在线TopN与同批未入库候选，后者用共享词召回，合计不超过60条；记录截断。

## SQL

无。

## Current behavior

单index增量，Top60，阈值默认0.1、共享词默认1；三策略；内容变化/部分失败可重检。未入库先写离线标记，insert_new时先确认插入；正文变更重建向量及待审，重写多模态正文需人工核实。

## Source

`src/kdb/retrieval/ingestion/conflict_jobs.py`
