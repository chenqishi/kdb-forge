# KnowledgeService

## 所属文件
`src/kdb/crud/service.py`

## 功能描述
文本级 CRUD 层。接收文本字段的文档/查询，生成向量与 _id、补齐旧 `process_one_data` 的业务副作用，委托 `KnowledgeRepository`。同时继承旧接口兼容层，保证旧 `SearchDataInterface` 调用方无需改方法名。

## 构造
- `__init__(repository, embedding_client, default_index=None, multimodal_prefix="", check_duplicate=None, is_need_llm=None, simility_tools=None, category_client=None, *, legacy_config=None)`。
  - `multimodal_prefix`：检索返回前替换 content 中 `[multimodal_prefix]` 占位；空串会删除占位符。
  - 显式 check_duplicate/is_need_llm 覆盖旧配置；未传取配置缺省。simility_tools 支持注入或懒加载，缺旧依赖时使用本地阈值实现，不静默跳过查重。
  - 第五个位置参数若为 Mapping，按合并前本地 legacy_config 解释；若为 bool/None，按远端查重开关解释。位置配置和 keyword legacy_config 重复传入则报错，不静默覆盖。兼容业务调用形式，不兼容 ES7 引擎。
  - category_client 注入对象只需提供 `map_cate_name_to_id(client, name)`；未注入则用已有通用类目接口，不依赖缺失的 `kdb.category` 包。
- `from_config(config_path, index_name=None) -> KnowledgeService`：显式索引 > default_index_name > test_index_name > engine 配置；测试/engine 回退会告警。旧配置读取 legacy_search_config_path 或 search_config_path。
- `legacy_config`：可选旧 search config；用于查重、类目 HTTP、默认参数和旧文件操作。

## 方法 Inputs/Outputs
- `insert_text(doc: Dict, index_name=None, refresh_imm=False) -> Tuple[bool, str]`
  - 流程：deepcopy → `_prepare_document(data, index_name=target_index)` → `repo.insert`
  - index_name 同时作为 `_prepare_document` 的 dataset 缺省值来源，与旧 `process_one_data(data, index_name=...)` 一致。
- `search_text(query: str, index_name=None, condition_dicts=None, size=10, search_type='qa', data_type='text', use_synonyms=False) -> Tuple[List[Dict], int]`
  - embed query → 默认条件填充（无条件时 quality_level=high/audit_result∈{1,2}；每条补 audit_result∈{1,2,-1}）→ `repo.search_multi(size=size*2)` → 每 doc 加 `similarity` 并把 content 中 `[multimodal_prefix]` 替换成实际前缀（与旧 `search_data_by_query` 一致）。**不排序不截断**。
- `update(data_id, doc, index_name=None, regenerate_embedding=False, refresh=False) -> bool`：局部合并 + 刷新 update_time；regenerate_embedding 时重算 title/content/indexes 向量。修改 title/synonyms 且未提供 indexes 时，先按同一 index 读取原文档，同步派生检索项并保留其他自定义/图片项；读不到则拒绝写入。显式 indexes 仍是调用方的替换列表。清空根文本时向量置 null，避免旧向量残留；refresh=True 时强制刷新索引。
- `delete(data_id, index_name=None, refresh=False) -> bool`。
- `get(data_id, index_name=None) -> Optional[Dict]`。
- `search_text_multi`、`web_search`、`batch_insert`：保留远端新增名称，统一委托兼容层的多查询、分页和批量实现；index 参数支持字符串或列表，不复制另一套算法。
- `insert_data` 不修改调用方字典，保持远端修复；处理异常返回 `(False, '数据处理失败')`。查重覆盖时软删异常记录后仍尝试写入，ES8 按 `_id` 使用 ids 查询。

## 内部方法
- `_prepare_document(data, index_name=None) -> Dict`：
  1. 非 schema 字段归入 ext_info（依据 `SCHEMA_FIELDS`）；
  2. `is_audit→audit_result` 迁移；新建时补 audit_result/quality_level；truthy 非法 audit_result 无论有无 _id 都矫正，合法 2 保留，quality_level 矫正仅用于新建；
  3. indexes/image_indexes 初始化 + 冗余构造（image_indexes.text、title、synonyms_title 合入 indexes）；
  4. indexes/image_indexes 向量化；
  5. **multimodal_contents → content 拼接**（`_join_multimodal_contents`，必须在 title/content 向量化之前）；
  6. title/content 向量化（`.tolist()`）；
  7. **keywords 缺省**：基于 `legacy_gen_keyword_by_title_content`（jieba.analyse.textrank，本地零外部调用）；只吞 ImportError，运行异常上抛；
  8. 空 indexes 清理；
  9. segment 去 title/synonyms_title；
  10. 时间字段（insert_time 仅新建；update_time 总刷新）；
  11. 新建时 from_type/from_type_norm/tags 缺省；非字符串 from_type 不分新旧都转 str；from_type_norm 运行异常上抛；tags 缺省=keywords；
  12. `del_flag=0`（底层引擎存储契约，新建必填）；
  13. category_infos[].category_id 强制 str、显式类目树解析、primary_category 和默认分组；不执行挖掘侧的 Payoneer Olive 推断；
  14. dataset 缺省 = index_name；
  15. `_id = gen_data_id`（仅新建）。
- `_join_multimodal_contents(multimodal_contents)`：与旧 `SearchDataInterface.join_multimodal_contents` 等价；file/image/video/audio 用字面 `[multimodal_prefix]` 占位，由 search_text 阶段替换。
- `_cal_similarity / _cal_title_similarity`：复刻旧实现，复用 `cosine_similarity`。qa：有 title → `title_sim + 0.2*content_sim`，否则 content_sim；非 qa → max；data_type 含 image → 叠加 image_indexes 最大相似度。

## 兼容层
- `SearchDataInterface` 兼容类支持旧的 `search_engine/config_path/**kwargs` 构造方式。
- 旧公开方法（insert_data、search_data、search_data_by_query、search_data_by_multi_query、
  web_search_data、批量插入、查重、类目和按文件操作）由 `LegacySearchDataInterfaceMixin` 提供；
  外部类目 HTTP 和 SimilityTools 使用旧配置，但 ES 数据请求统一走 ES8.17 路由引擎。

## 关键依赖
- `kdb.crud.repository.KnowledgeRepository`
- `kdb.embedding.client.EmbeddingClient`（注入）
- `kdb.crud.ids.gen_data_id`、`kdb.legacy_bridge.cosine_similarity`
- `kdb.legacy_bridge.legacy_gen_keyword_by_title_content`（jieba 本地）、`legacy_get_from_norm_type`（规则映射）

## SQL
不读写 SQL。
