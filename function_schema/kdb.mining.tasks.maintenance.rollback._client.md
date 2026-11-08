# kdb.mining.tasks.maintenance.rollback._client

## Signature

`_client(config_path: str)`

## Inputs

ES HTTP 配置路径。

## Outputs

返回 EsHttpClient.from_config 的对象。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/tasks/maintenance/rollback.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
