# kdb.mining.bridges.retrieval.build_search_interface

## Signature

`build_search_interface(search_config_path: str=DEFAULT_SEARCH_CONFIG)`

## Inputs

检索主配置路径；默认值由 bridges/defaults.py 提供。

## Outputs

返回唯一类型 SearchDataInterface 的实例；保留其真实初始化与异常行为。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/bridges/retrieval.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
