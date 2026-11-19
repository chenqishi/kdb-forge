# kdb.mining.document.workflows.deduplication.prepare_document_dedup

## Signature

`prepare_document_dedup(controller)`

## Inputs

解析后按task_info.document_dedup参数判断文档重复，输出报告；skip_new过滤映射，replace_old只保存旧快照。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Source

`src/kdb/mining/document/workflows/deduplication.py`
