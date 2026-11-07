# kdb.shared.clients.local_llm_adapter._ensure_llm_client

## Signature

`_ensure_llm_client(agents_root: Optional[str]=None)`

## Inputs

Existing function signature and business inputs are unchanged. Read together with the pre-existing function contract indexed by its original source prefix.

Existing optional agents_root argument; explicit KDB_LLM_CLIENT_PATH plugin path, optional KDB_LLM_CONFIG/AGENTS_LLM_CONFIG. No implicit external repository default.

## Outputs

Only dependency imports and canonical project/source/resource locations change. Runtime interfaces, business request parameters, output data, error/exit behavior and initialization timing remain those of the existing implementation. Service task launch and optional LLM plugin details are defined in off_task_app.* and local_llm_adapter.* contracts.

Load/cache only an explicitly selected plugin using the already documented configure_providers/request_llm interface. Preserve lazy initialization and graceful failure outputs; request_llm keeps image_urls support and 3-tuple return contract. See legacy_project/local_llm_adapter.request_knowledge_llm.md.

## SQL

No query, field, table, scoring or data mutation change. No backend or subprocess was kdb.mining.generation.run during migration validation.

None. No plugin loaded during offline verification; no model or backend request.

## Source

`src/kdb/shared/clients/local_llm_adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
