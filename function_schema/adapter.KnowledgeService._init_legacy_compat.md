# KnowledgeService._init_legacy_compat

## Inputs
`self, legacy_config: Optional[Mapping[str, Any]]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
Initialise attributes expected by old callers.

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
