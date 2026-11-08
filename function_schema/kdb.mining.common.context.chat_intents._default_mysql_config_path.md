# kdb.mining.common.context.chat_intents._default_mysql_config_path

## Signature

`_default_mysql_config_path() -> Optional[str]`

## Inputs

本项目配置根。

## Outputs

默认 mysql_conn_config.json 存在时返回路径，否则 None。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/common/context/chat_intents.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
