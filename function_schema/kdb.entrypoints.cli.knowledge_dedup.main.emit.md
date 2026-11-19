# kdb.entrypoints.cli.knowledge_dedup.main.emit

## Inputs

逐条flush JSONL检查结果，保留失败进度。

## Outputs

显式结构化结果；不把失败当完成。

## SQL / ES

无SQL。经单index检索/去重函数访问ES；服务端配置不可由工具参数覆盖。
