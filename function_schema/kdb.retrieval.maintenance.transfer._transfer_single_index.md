# kdb.retrieval.maintenance.transfer._transfer_single_index

## Signature

`_transfer_single_index(source_config_path, target_config_path, source_index_name, target_index_name, batch_size)`

## Inputs

源/目标检索配置、源/目标索引与批大小。

## Outputs

读取源索引，经目标 SearchDataInterface 重算向量并插入，返回 total_processed/success/failed/skipped 统计。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/retrieval/maintenance/transfer.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
