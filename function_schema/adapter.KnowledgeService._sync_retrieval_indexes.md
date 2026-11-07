# KnowledgeService._sync_retrieval_indexes

## Inputs
`data: Dict[str, Any], existing: Dict[str, Any]`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
同步修改后的检索文本，同时保留自定义和图片检索项。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
