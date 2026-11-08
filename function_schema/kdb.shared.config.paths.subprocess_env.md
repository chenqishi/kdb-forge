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

`src/kdb/shared/config/paths.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
