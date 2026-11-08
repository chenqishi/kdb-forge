# tests.offline.test_business_boundaries.test_launchers_and_task_commands_resolve_to_executable_modules

## Signature

`test_launchers_and_task_commands_resolve_to_executable_modules()`

## Inputs

合成数据、临时目录与 pytest 替身；不访问线上服务。

## Outputs

六个 HTTP 入口与任务命令对应现存可执行模块，CLI 保留 __main__ 入口。

## SQL

无直接 SQL；外部依赖在测试中由替身隔离。

## Source

`tests/offline/test_business_boundaries.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
