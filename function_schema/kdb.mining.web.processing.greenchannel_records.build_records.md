# kdb.mining.web.processing.greenchannel_records.build_records

## Signature

`build_records(manifest_path, category_map)`

## Inputs

网页 manifest 路径与平台到类目的映射。

## Outputs

每个有效板块产生一条 ES 记录；保留文本长度门槛、模板字段与排序。此函数本身不写 ES。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/web/processing/greenchannel_records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
