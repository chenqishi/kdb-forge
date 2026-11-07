# KnowledgeRepository.count_by_query

## Inputs
`self, index_name: str, query: Dict[str, Any]`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
Count a supplied index and raw DSL without index creation or defaults.

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
