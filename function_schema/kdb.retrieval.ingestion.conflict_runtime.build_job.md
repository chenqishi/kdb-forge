# kdb.retrieval.ingestion.conflict_runtime.build_job

## Signature

`build_job(index, *, config_path=None, search_config_path=None, journal=None, interface=None)`

## Inputs

根据显式检索/模型配置构建原SearchDataInterface、单index Store和DedupJob；模型/策略默认来自配置。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Source

`src/kdb/retrieval/ingestion/conflict_runtime.py`
