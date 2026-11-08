# kdb.shared.config.paths.resource_path

## Signature

`resource_path(*parts)`

## Inputs

`*parts`: explicit path components.

## Outputs

Return RESOURCES_ROOT (project/resources) joined with resource components. No fallback to root legacy directories.

## SQL

None. Pure local path/environment construction.

## Source

`src/kdb/shared/config/paths.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
