# kdb.services.forge_compat.adapter.KnowledgeService._regenerate_embeddings

## Signature

`KnowledgeService._regenerate_embeddings(self, data: Dict[str, Any]) -> None`

## Inputs

`self, data: Dict[str, Any]`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

Mutable patch with optional title/content/indexes; injected embedding client.

## Outputs

更新时按需重算向量（仅对传入的 title/content/indexes 生效）。

Recalculates vectors for supplied text fields and index entries. Empty root text
sets its vector to null so an ES partial update cannot retain the old vector.
Embedding failures propagate before a write. Does not modify absent root fields.

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

None; embedding client calls only.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
