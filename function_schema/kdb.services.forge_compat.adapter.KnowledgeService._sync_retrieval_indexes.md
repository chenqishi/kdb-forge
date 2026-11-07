# kdb.services.forge_compat.adapter.KnowledgeService._sync_retrieval_indexes

## Signature

`KnowledgeService._sync_retrieval_indexes(data: Dict[str, Any], existing: Dict[str, Any]) -> None`

## Inputs

Mutable partial document and stored document. Called only for title/synonyms
updates with regenerate_embedding and no explicit indexes in the patch.
Index entries follow existing {text, embedding, ...} schema from _prepare_document.

`data: Dict[str, Any], existing: Dict[str, Any]`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

Sets patch.indexes: removes obsolete title/synonym-derived text entries, adds
current title/synonyms, preserves custom entries and image-derived texts. A text
also present in retained synonyms/image indexes is not removed. As in insertion,
entries are identified by text; no index provenance field is introduced.
Does not mutate the stored document; vector regeneration is performed afterwards.

同步修改后的检索文本，同时保留自定义和图片检索项。

## SQL

None; pure in-memory preparation.

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
