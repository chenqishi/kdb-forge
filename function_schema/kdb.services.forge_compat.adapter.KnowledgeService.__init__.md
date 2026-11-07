# kdb.services.forge_compat.adapter.KnowledgeService.__init__

## Signature

`KnowledgeService.__init__(self, repository: KnowledgeRepository, embedding_client: Optional[EmbeddingClient], default_index: Optional[str]=None, multimodal_prefix: str='', check_duplicate: Optional[Union[bool, Mapping[str, Any]]]=None, is_need_llm: Optional[bool]=None, simility_tools: Any=None, category_client: Any=None, *, legacy_config: Optional[Dict[str, Any]]=None) -> None`

## Inputs

`self, repository: KnowledgeRepository, embedding_client: Optional[EmbeddingClient], default_index: Optional[str]=None, multimodal_prefix: str='', check_duplicate: Optional[Union[bool, Mapping[str, Any]]]=None, is_need_llm: Optional[bool]=None, simility_tools: Any=None, category_client: Any=None, *, legacy_config: Optional[Dict[str, Any]]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

repository、embedding_client、default_index、multimodal_prefix；远端新增的
check_duplicate/is_need_llm/simility_tools/category_client 注入参数，以及 keyword-only
legacy_config。第五个位置参数兼容合并前本地的 Mapping 配置，以及远端的 bool/None
查重开关；Mapping 与 keyword legacy_config 同时传入时抛 TypeError，避免静默丢配置。
显式开关覆盖 legacy_config，None 使用旧配置缺省。这里兼容的是业务配置调用形式，
不是 ES7 客户端或 ES7 查询。
category_client 仅要求已有的 map_cate_name_to_id(client, name) 协议；未注入复用本地类目接口。
embedding_client 可为 None，仅供 from_count_config 创建的统计专用实例；普通文本/向量操作仍需 embedding。

## Outputs

Thin protocol forwarding to the single published implementation; preserves normal return values and exceptions.

初始化新式 CRUD 和旧接口兼容属性。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

无。

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
