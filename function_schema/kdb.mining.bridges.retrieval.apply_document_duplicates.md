# kdb.mining.bridges.retrieval.apply_document_duplicates

## Signature

`apply_document_duplicates(job, report, policy)`

## Inputs

bridge执行已捕获旧文档知识的软删。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Source

`src/kdb/mining/bridges/retrieval.py`
