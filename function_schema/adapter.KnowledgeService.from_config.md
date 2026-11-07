# KnowledgeService.from_config

## Inputs
`cls, config_path: str, index_name: Optional[str]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
从 rebuild config（config_test.json）构造完整 Service。

若 cfg 中含 `legacy_search_config_path` 指向旧 `config_for_search_index.json`，则从中
读取 `multimodal_prefix` 自动注入，保证 search 返回与旧 `search_data_by_query` 一致。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
