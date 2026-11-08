# kdb.shared.config.paths.source_path

## Signature

`source_path(*parts)`

## Inputs

`*parts`: explicit path components.

## Outputs

Return SOURCE_ROOT (project/src) joined with canonical source components; callers include kdb in the components. No old source mapping.

## SQL

None. Pure local path/environment construction.

## Source

`src/kdb/shared/config/paths.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
