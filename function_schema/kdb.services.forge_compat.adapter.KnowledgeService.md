# kdb.services.forge_compat.adapter.KnowledgeService

## Signature

`KnowledgeService(self, repository: KnowledgeRepository, embedding_client: Optional[EmbeddingClient], default_index: Optional[str]=None, multimodal_prefix: str='', check_duplicate: Optional[Union[bool, Mapping[str, Any]]]=None, is_need_llm: Optional[bool]=None, simility_tools: Any=None, category_client: Any=None, *, legacy_config: Optional[Dict[str, Any]]=None)`

## Inputs

保留公开构造的 repository、embedding_client、default_index、multimodal_prefix、check_duplicate、is_need_llm、simility_tools、category_client 与 keyword-only legacy_config。第五位置 Mapping 按配置解释；重复提供配置抛 TypeError。显式开关优先于配置。

## Outputs

协议层委托唯一 SearchDataInterface 与 Repository；不复制检索、类目、查重和入库算法。from_config 保留显式索引、default_index_name、test_index_name、引擎默认的优先级及两种搜索配置键。from_count_config 不加载 embedding 或创建索引。update 保留重算、已有检索项同步及成功后刷新语义。各方法详细约束见同模块逐函数契约。

## SQL

无直接 SQL。知识读写通过 Repository 委托 Elasticsearch；模型和类目接口按原请求阶段调用。

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
