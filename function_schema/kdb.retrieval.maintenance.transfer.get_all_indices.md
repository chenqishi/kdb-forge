# kdb.retrieval.maintenance.transfer.get_all_indices

## Signature

`get_all_indices(es_config_path)`

## Inputs

包含 search_engine_config_path 的配置文件。

## Outputs

通过原 ES cat.indices 获得索引名，过滤点号开头的系统索引；保留异常处理。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/retrieval/maintenance/transfer.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
