# kdb.retrieval.ingestion.conflict_runtime.load_config

## Signature

`load_config(path=None)`

## Inputs

读取显式配置/KDB_DEDUP_CONFIG，凭据支持api_key_env；不复制其他仓库配置或隐式密钥。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Source

`src/kdb/retrieval/ingestion/conflict_runtime.py`
