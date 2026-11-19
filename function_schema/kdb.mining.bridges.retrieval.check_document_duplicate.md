# kdb.mining.bridges.retrieval.check_document_duplicate

## Signature

`check_document_duplicate(job, name, parsed, **kwargs)`

## Inputs

bridge调用文档查重，保持检索域不反向依赖挖掘。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Source

`src/kdb/mining/bridges/retrieval.py`
