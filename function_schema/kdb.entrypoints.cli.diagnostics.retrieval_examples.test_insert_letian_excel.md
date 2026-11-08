# kdb.entrypoints.cli.diagnostics.retrieval_examples.test_insert_letian_excel

## Signature

`test_insert_letian_excel(data_file: str, config_path: str)`

## Inputs

data_file 的 question/answer/synonyms_query 等字段及检索配置。

## Outputs

读取本地记录，按保留的 RakutenFrance 配置执行实际插入并记录结果；这不是离线测试函数。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/entrypoints/cli/diagnostics/retrieval_examples.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
