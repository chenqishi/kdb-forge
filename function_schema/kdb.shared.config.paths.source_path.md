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

`src/kdb/shared/config/paths.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
