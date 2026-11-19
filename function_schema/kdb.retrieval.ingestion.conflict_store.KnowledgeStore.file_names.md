# kdb.retrieval.ingestion.conflict_store.KnowledgeStore.file_names

## Signature

`KnowledgeStore.file_names(self)`

## Inputs

枚举同一index内document/html/manual来源文件名（不限审核）；使用在线引擎scroll，名称去重，不截断。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Current behavior

同index ES8边界，候选不限platform/审核，目标可筛audit_result=-1/时间/task_id/未完成。修改先journal，再核对内容/审核及CAS版本；非NotFound读取失败不可隐藏。

## Source

`src/kdb/retrieval/ingestion/conflict_store.py`
