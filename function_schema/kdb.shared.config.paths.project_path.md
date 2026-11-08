# kdb.shared.config.paths.project_path

## Signature

`project_path(*parts)`

## Inputs

`*parts`: explicit path components.

## Outputs

Return PROJECT_ROOT joined with explicit project-relative components. No file creation or directory change.

## SQL

None. Pure local path/environment construction.

## Source

`src/kdb/shared/config/paths.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
