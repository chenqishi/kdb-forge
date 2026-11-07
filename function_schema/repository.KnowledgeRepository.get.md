# KnowledgeRepository.get

## Inputs
`self, data_id: str, index_name: Optional[str]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
按 _id 取文档；返回 `{"_id":..., **_source}` 或 None。委托旧 `engine.get`。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
