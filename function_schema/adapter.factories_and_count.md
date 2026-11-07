# KnowledgeService factories and count protocol

## Inputs
Original forge `from_config(config_path, index_name=None)`, `from_count_config(config_path)`, `_load_legacy_search_cfg(cfg)`, `get_from_type_count(index_name,start=None,end=None,from_type="chat_auto")` signatures and config priority.

## Outputs
Original factory construction and errors; ordinary config retains both legacy_search_config_path/search_config_path and original missing-config fallback. Count uses exact original single-index validation and fixed high/source native count, empty index yields true/0. Count-only published ES8 engine receives both ensure_index=False and extra_params.ensure_index_on_init=False. No temporary configuration or SearchDataInterface initialization is introduced.

## SQL
None. Local JSON configuration and existing ES8 engine factory/native count only.

## Source
Original forge source snapshot at `/root/kdb-forge-refactor-baselines/20261105-r1/kdb-forge/content/src/kdb/crud/service.py`; original schemas retained under function_schema/forge_protocol/.
