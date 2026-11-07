# KnowledgeService.search_data_by_query

## Inputs
`self, query: str, index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, size: int=10, search_type: str='qa', data_type: str='text', use_synonyms: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
Thin protocol forwarding to the single published implementation; preserves normal return values and exceptions.

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
