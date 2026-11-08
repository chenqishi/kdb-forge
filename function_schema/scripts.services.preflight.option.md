# scripts.services.preflight.option

## Signature

`option(argv, name, default=None)`

## Inputs

`argv, name, default=None`

## Outputs

Support function under the startup/preflight contract, preserving argv/cwd and explicitly simulated external boundaries.
See preflight.module.md for exact side effects and validation scope.

## SQL

No real SQL. Config validation is local only; startup tests substitute the SQL pool before original constructor execution.

## Source

`scripts/services/preflight.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
