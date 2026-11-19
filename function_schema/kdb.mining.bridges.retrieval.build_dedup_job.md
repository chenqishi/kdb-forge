# kdb.mining.bridges.retrieval.build_dedup_job

## Signature

`build_dedup_job(index, **kwargs)`

## Inputs

挖掘域到检索域唯一bridge，返回已配置去重job。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Source

`src/kdb/mining/bridges/retrieval.py`
