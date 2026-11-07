# KnowledgeRepository.search_by_page

## Inputs
`self, query_dict: Dict[str, Any], index_name: Optional[Union[str, List[str]]]=None, size: int=10, page_num: int=1, score_threshold: Optional[float]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
分页 + score_threshold 过滤检索，返回 (docs, total_num)。委托旧 `engine.search_multi_by_page`。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
