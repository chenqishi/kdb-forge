# scripts.services.preflight.probe_module

## Signature

`probe_module(name)`

## Inputs

`name`

## Outputs

Support function under the startup/preflight contract, preserving argv/cwd and explicitly simulated external boundaries.
See preflight.module.md for exact side effects and validation scope.

## SQL

No real SQL. Config validation is local only; startup tests substitute the SQL pool before original constructor execution.

## Source

`scripts/services/preflight.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
