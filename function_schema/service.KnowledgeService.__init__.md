# KnowledgeService.__init__

## Inputs
repository、embedding_client、default_index、multimodal_prefix；远端新增的
check_duplicate/is_need_llm/simility_tools/category_client 注入参数，以及 keyword-only
legacy_config。第五个位置参数兼容合并前本地的 Mapping 配置，以及远端的 bool/None
查重开关；Mapping 与 keyword legacy_config 同时传入时抛 TypeError，避免静默丢配置。
显式开关覆盖 legacy_config，None 使用旧配置缺省。这里兼容的是业务配置调用形式，
不是 ES7 客户端或 ES7 查询。
category_client 仅要求已有的 map_cate_name_to_id(client, name) 协议；未注入复用本地类目接口。

## Outputs
初始化新式 CRUD 和旧接口兼容属性。

## SQL
无。
