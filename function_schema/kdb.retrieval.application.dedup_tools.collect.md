# kdb.retrieval.application.dedup_tools.collect

## Signature

`collect(job, args)`

## Inputs

限量收集选定scope并关闭scroll，报告是否截断。

## Outputs

显式结构化结果；不把失败当完成。

## SQL / ES

无SQL。经单index检索/去重函数访问ES；服务端配置不可由工具参数覆盖。

## Current behavior

六个工具复用快速、增量及文档流程；principal由服务器提供，必须admin+leader及index授权，写入另需allow_mutations；不接受模型传入身份。

## Source

`src/kdb/retrieval/application/dedup_tools.py`
