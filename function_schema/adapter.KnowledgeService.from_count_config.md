# KnowledgeService.from_count_config

## Inputs
`cls, config_path: str`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
Build a count-only service with no ensure, embedding or legacy config I/O.

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
