# kdb.services.forge_compat.bootstrap.build_legacy_engine

## Signature

`build_legacy_engine(config_path=None, index_name=None, **kwargs)`

## Inputs

`config_path=None`, `index_name=None`, and existing engine keyword arguments.

## Outputs

Lazily construct the same RoutedLegacyEngine from kdb.services.forge_compat.engine. Constructor arguments and engine selection/counting/retrieval behavior remain unchanged. No external workspace lookup or path injection. 

## SQL

No query/schema change. Existing engine construction behavior is retained; no client constructed during migration checks.

## Source

`src/kdb/services/forge_compat/bootstrap.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
