# KnowledgeRepository.insert

## Inputs
`self, data: Dict[str, Any], index_name: Optional[str]=None, refresh_imm: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
插入/upsert 一条文档。

前置约定：data 必须含 `_id`；`indexes[].embedding` 已是 1024 维 list。
委托 ES8 `engine.insert`（校验维度、过滤零向量、update(doc_as_upsert=True)）。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
