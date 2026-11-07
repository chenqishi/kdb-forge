# kdb.shared.config.paths.subprocess_env

## Signature

`subprocess_env(base=None)`

## Inputs

`base=None`: optional environment mapping.

## Outputs

Return a copy of os.environ (or explicit base mapping) with this project/src prepended once to existing PYTHONPATH. Preserve all other environment values. Do not add the project root or any external repository.

## SQL

None. Pure local path/environment construction.

## Source

`src/kdb/shared/config/paths.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
