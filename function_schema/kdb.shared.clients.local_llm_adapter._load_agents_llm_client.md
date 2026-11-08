# kdb.shared.clients.local_llm_adapter._load_agents_llm_client

## Signature

`_load_agents_llm_client(agents_root: str)`

## Inputs


Existing optional agents_root argument; explicit KDB_LLM_CLIENT_PATH plugin path, optional KDB_LLM_CONFIG/AGENTS_LLM_CONFIG. No implicit external repository default.

## Outputs


Load/cache only an explicitly selected plugin using the already documented configure_providers/request_llm interface. Preserve lazy initialization and graceful failure outputs; request_llm keeps image_urls support and 3-tuple return contract. See kdb.shared.clients.local_llm_adapter.request_knowledge_llm.md.

## SQL


None. No plugin loaded during offline verification; no model or backend request.

## Source

`src/kdb/shared/clients/local_llm_adapter.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
