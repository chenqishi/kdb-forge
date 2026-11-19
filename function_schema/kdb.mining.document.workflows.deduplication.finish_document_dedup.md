# kdb.mining.document.workflows.deduplication.finish_document_dedup

## Signature

`finish_document_dedup(controller)`

## Inputs

所有生成/插入阶段成功后才按旧快照软删；review_only禁止replace_old。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Source

`src/kdb/mining/document/workflows/deduplication.py`
