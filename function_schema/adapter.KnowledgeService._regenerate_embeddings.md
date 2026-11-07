# KnowledgeService._regenerate_embeddings

## Inputs
`self, data: Dict[str, Any]`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
更新时按需重算向量（仅对传入的 title/content/indexes 生效）。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
