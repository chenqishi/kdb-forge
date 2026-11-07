# kdb.services.forge_compat.adapter.KnowledgeService.from_count_config

## Signature

`KnowledgeService.from_count_config(cls, config_path: str) -> 'KnowledgeService'`

## Inputs

Existing function signature and business inputs are unchanged. Read together with the pre-existing function contract indexed by its original source prefix.

`cls, config_path: str`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

运行配置路径；读取 engine_config_path 及可选 default_index_name/test_index_name。

## Outputs

Only dependency imports and canonical project/source/resource locations change. Runtime interfaces, business request parameters, output data, error/exit behavior and initialization timing remain those of the existing implementation. Service task launch and optional LLM plugin details are defined in off_task_app.* and local_llm_adapter.* contracts.

Build a count-only service with no ensure, embedding or legacy config I/O.

构造真实 RoutedLegacyEngine、Repository、KnowledgeService 的统计专用实例。
同时传入 ensure_index=False 和 extra_params.ensure_index_on_init=False，覆盖配置中的建库开关。
embedding_client 为 None；不调用普通 from_config、不读取 embedding/legacy search 配置。
引擎仍校验已有 ES8.17 配置、默认索引与 vector_fields；初始化错误由 API 转为失败响应。

## SQL

No query, field, table, scoring or data mutation change. No backend or subprocess was kdb.mining.generation.run during migration validation.

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

无。读取本地配置，创建 ES 客户端；不请求 ES、不建库、不更新 mapping。

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
