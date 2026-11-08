# scripts.testing.offline_guard.prepare_paths

## Signature

`prepare_paths(root)`

## Inputs

当前项目root，private/test_dependencies可提供独立测试SDK。

## Outputs

导入路径仅为src、当前项目根、scripts/testing；跨测试fixture使用tests.<domain>包导入，不引入其他工作区路径。确认elasticsearch8.17并输出实际SDK路径。

## SQL

无SQL/网络；install先启用禁止外部IO/子进程的guard。

## Source

`scripts/testing/offline_guard.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
