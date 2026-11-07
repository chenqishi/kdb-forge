# KnowledgeService.web_search_data

## Inputs
`self, query: str, client: str=None, index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, page_size: int=None, page_num: int=1, score_threshold: float=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
Thin protocol forwarding to the single published implementation; preserves normal return values and exceptions.

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
