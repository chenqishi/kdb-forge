# kdb.shared.config.global_config._load_global_config

## Signature

`_load_global_config()`

## Inputs

本项目 _DEFAULT_CONFIG 与 PROJECT_ROOT。

## Outputs

委托 load_global_config 深复制默认值、读取本项目 config/global_config.json 并浅覆盖；异常回退。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/shared/config/global_config.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
