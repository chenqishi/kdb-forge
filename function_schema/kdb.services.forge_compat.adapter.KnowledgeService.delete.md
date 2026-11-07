# kdb.services.forge_compat.adapter.KnowledgeService.delete

## Signature

`KnowledgeService.delete(self, document_id, index_name=None, refresh=False)`

## Inputs

`self, document_id, index_name=None, refresh=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

Thin protocol forwarding to the single published implementation; preserves normal return values and exceptions.

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
