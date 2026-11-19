# kdb.retrieval.ingestion.document_dedup.apply_document_matches

## Signature

`apply_document_matches(store, report, policy='record_only')`

## Inputs

record_only/skip_new/replace_old；replace_old只软删检查时捕获的旧文件知识快照，journal+CAS，失败外抛。

## Outputs

见源码签名；返回结构化结果，失败显式报告。

## SQL / ES

不直接访问SQL。通过检索域单index Store读写ES，文档名字段ext_info.from_file_name，删除为del_flag=1并记原因；原任务状态更新契约保持不变。

## Current behavior

名称或450字同文档segment覆盖>=0.7命中；覆盖取位置并集，不混QA或不同文件。替换仅处理捕获的旧ID。

## Source

`src/kdb/retrieval/ingestion/document_dedup.py`
