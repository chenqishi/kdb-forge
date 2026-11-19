# kdb.entrypoints.cli.knowledge_dedup.read_records

## Signature

`read_records(path, kind, only_unchecked=True)`

## Inputs

流式读取JSONL（单行限2MiB），要求指定data_type，标记为未入库，支持恢复上次标记。

## Outputs

显式结构化结果；不把失败当完成。

## SQL / ES

无SQL。经单index检索/去重函数访问ES；服务端配置不可由工具参数覆盖。

## Current behavior

离线CLI，JSONL有界逐条处理、报告及summary、带标记knowledge和ready产物；默认record_only，dry_run/estimate-only只预览或估算，失败退出2。

## Source

`src/kdb/entrypoints/cli/knowledge_dedup.py`
