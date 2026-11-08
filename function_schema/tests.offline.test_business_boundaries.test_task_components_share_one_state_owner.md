# tests.offline.test_business_boundaries.test_task_components_share_one_state_owner

## Signature

`test_task_components_share_one_state_owner()`

## Inputs

合成数据、临时目录与 pytest 替身；不访问线上服务。

## Outputs

进程、队列、资源、记录模块引用同一 tasks.state 对象。

## SQL

无直接 SQL；外部依赖在测试中由替身隔离。

## Source

`tests/offline/test_business_boundaries.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
