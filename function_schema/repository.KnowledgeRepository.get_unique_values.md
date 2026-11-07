# KnowledgeRepository.get_unique_values

## Inputs
`self, field_name: str, index_name: Optional[str]=None, size: int=10000, include_doc_count: bool=False, extra_query: Optional[Dict[str, Any]]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
聚合获取某字段唯一值集合。委托旧 `engine.get_unique_values`。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
