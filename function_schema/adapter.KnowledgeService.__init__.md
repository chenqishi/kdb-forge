# KnowledgeService.__init__

## Inputs
`self, repository: KnowledgeRepository, embedding_client: Optional[EmbeddingClient], default_index: Optional[str]=None, multimodal_prefix: str='', check_duplicate: Optional[Union[bool, Mapping[str, Any]]]=None, is_need_llm: Optional[bool]=None, simility_tools: Any=None, category_client: Any=None, *, legacy_config: Optional[Dict[str, Any]]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
Thin protocol forwarding to the single published implementation; preserves normal return values and exceptions.

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
