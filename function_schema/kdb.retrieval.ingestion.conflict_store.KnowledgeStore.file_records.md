# kdb.retrieval.ingestion.conflict_store.KnowledgeStore.file_records

## Signature

`KnowledgeStore.file_records(self, name)`

## Inputs

按原文件名精确查询并捕获待替换所有QA/segment；不匹配supersedes别名，不包含chat来源。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Current behavior

同index ES8边界，候选不限platform/审核，目标可筛audit_result=-1/时间/task_id/未完成。修改先journal，再核对内容/审核及CAS版本；非NotFound读取失败不可隐藏。

## Source

`src/kdb/retrieval/ingestion/conflict_store.py`
