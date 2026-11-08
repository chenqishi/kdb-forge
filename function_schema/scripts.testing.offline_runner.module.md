# scripts.testing.offline_runner.module

## Inputs

当前 tests 目录；可选 KDB_TEST_PYTHON、--group smoke/retrieval/mining/audit/jobs/integrations/shared/services/all/explicit 与 pytest 参数。

## Outputs

导入业务前安装守卫；默认 all 与 --group all 均收集整个 tests；smoke 仅显式选择 entry_smoke/offline，explicit 需要实际 tests 路径。关闭插件自动加载，转发 pytest 退出码。两例 requires_process 测试默认明确打印并排除，原业务断言保留。网络、监听、DNS、子进程和非允许目录写入受限，不能通过扩大选择关闭守卫。

## SQL

无 SQL/ES 构造；仅本地测试环境与路径准备。

## Source

`scripts/testing/offline_runner.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
