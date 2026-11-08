# kdb.retrieval.maintenance.transfer.transfer_es_data

## Signature

`transfer_es_data(source_config_path, target_config_path, source_index_name, target_index_name, batch_size=100)`

## Inputs

源/目标检索配置、源/目标索引，batch_size 默认 100。

## Outputs

沿原迁移流程读取并写目标索引，旧 embedding 不直接复制，保留初始化失败与日志行为。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/retrieval/maintenance/transfer.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
