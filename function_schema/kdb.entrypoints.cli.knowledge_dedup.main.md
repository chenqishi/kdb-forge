# kdb.entrypoints.cli.knowledge_dedup.main

## Signature

`main(argv=None)`

## Inputs

knowledge/document子命令；显式index及输出路径，默认record_only，可dry-run/estimate-only；失败退出2，逐条报告、summary及离线knowledge输出。

## Outputs

显式结构化结果；不把失败当完成。

## SQL / ES

无SQL。经单index检索/去重函数访问ES；服务端配置不可由工具参数覆盖。

## Current behavior

离线CLI，JSONL有界逐条处理、报告及summary、带标记knowledge和ready产物；默认record_only，dry_run/estimate-only只预览或估算，失败退出2。

## Source

`src/kdb/entrypoints/cli/knowledge_dedup.py`
