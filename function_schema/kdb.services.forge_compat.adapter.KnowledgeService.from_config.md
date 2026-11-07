# kdb.services.forge_compat.adapter.KnowledgeService.from_config

## Signature

`KnowledgeService.from_config(cls, config_path: str, index_name: Optional[str]=None) -> 'KnowledgeService'`

## Inputs

`cls, config_path: str, index_name: Optional[str]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

重构配置路径、可选 index_name。

## Outputs

从 rebuild config（config_test.json）构造完整 Service。

若 cfg 中含 `legacy_search_config_path` 指向旧 `config_for_search_index.json`，则从中
读取 `multimodal_prefix` 自动注入，保证 search 返回与旧 `search_data_by_query` 一致。

加载 ES8.17 Repository、embedding client 和旧服务兼容配置后的 KnowledgeService。
默认索引优先级：显式参数 > default_index_name > test_index_name > engine 配置；
回退到测试索引/engine 时告警。旧配置从 legacy_search_config_path/search_config_path 读取。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

无；读取本地 JSON 配置。

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
