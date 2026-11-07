# kdb.services.forge_compat.adapter.KnowledgeService._from_interface

## Signature

`KnowledgeService._from_interface(cls, interface, default_index=None, *, legacy_config=None)`

## Inputs

`cls, interface, default_index=None, *, legacy_config=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

Bind an already initialized canonical object without reinitializing it.

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
