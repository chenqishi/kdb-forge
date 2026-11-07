# KnowledgeService._load_legacy_search_cfg

## Inputs
`cfg: Dict[str, Any]`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
Read the optional legacy service config without hiding missing configuration.

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
