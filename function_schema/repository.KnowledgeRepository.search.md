# KnowledgeRepository.search

## Inputs
`self, query_dict: Dict[str, Any], size: int=10, index_name: Optional[Union[str, List[str]]]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
单引擎原始混合检索（不重排）。委托旧 `engine.search`。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
