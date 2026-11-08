# tests.offline.test_business_boundaries.test_business_import_directions_and_cycles

## Signature

`test_business_import_directions_and_cycles()`

## Inputs

合成数据、临时目录与 pytest 替身；不访问线上服务。

## Outputs

所有实际核心模块的禁止依赖边和静态循环均为空。

## SQL

无直接 SQL；外部依赖在测试中由替身隔离。

## Source

`tests/offline/test_business_boundaries.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
