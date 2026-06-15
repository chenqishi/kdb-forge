# KnowledgeService

## 所属文件
`src/kdb/crud/service.py`

## 功能描述
文本级 CRUD 层。接收文本字段的文档/查询，生成向量与 _id、补齐 `process_one_data` 中**纯本地**的业务默认（jieba 关键词、from_type_norm、多模态拼接等），委托 `KnowledgeRepository`。注入 `EmbeddingClient`。向量化、业务默认与相似度逐行复刻旧 `search_index_data_interface.py`，保证与旧 `SearchDataInterface` 对齐。

## 构造
- `__init__(repository: KnowledgeRepository, embedding_client: EmbeddingClient, default_index=None, multimodal_prefix: str = "")`
  - `multimodal_prefix`：`search_text` 返回前替换 content 中 `[multimodal_prefix]` 占位的真实前缀；与旧 `SearchDataInterface.multimodal_prefix` 一致；空串等效不替换。
- `from_config(config_path, index_name=None) -> KnowledgeService`：从 config_test.json 构造；若 cfg 含 `legacy_search_config_path` 自动读取 `multimodal_prefix` 注入。

## 方法 Inputs/Outputs
- `insert_text(doc: Dict, index_name=None, refresh_imm=False) -> Tuple[bool, str]`
  - 流程：deepcopy → `_prepare_document(data, index_name=target_index)` → `repo.insert`
  - index_name 同时作为 `_prepare_document` 的 dataset 缺省值来源，与旧 `process_one_data(data, index_name=...)` 一致。
- `search_text(query: str, index_name=None, condition_dicts=None, size=10, search_type='qa', data_type='text', use_synonyms=False) -> Tuple[List[Dict], int]`
  - embed query → 默认条件填充（无条件时 quality_level=high/audit_result∈{1,2}；每条补 audit_result∈{1,2,-1}）→ `repo.search_multi(size=size*2)` → 每 doc 加 `similarity` 并把 content 中 `[multimodal_prefix]` 替换成实际前缀（与旧 `search_data_by_query` 一致）。**不排序不截断**。
- `update(data_id, doc, index_name=None, regenerate_embedding=False, refresh=False) -> bool`：局部合并 + 刷新 update_time；regenerate_embedding 时重算 title/content/indexes 向量；refresh=True 时强制刷新索引。
- `delete(data_id, index_name=None, refresh=False) -> bool`。
- `get(data_id, index_name=None) -> Optional[Dict]`。

## 内部方法
- `_prepare_document(data, index_name=None) -> Dict`：
  1. 非 schema 字段归入 ext_info（依据 `SCHEMA_FIELDS`）；
  2. `is_audit→audit_result` 迁移；新建时 audit_result/quality_level 缺省与合法性矫正；
  3. indexes/image_indexes 初始化 + 冗余构造（image_indexes.text、title、synonyms_title 合入 indexes）；
  4. indexes/image_indexes 向量化；
  5. **multimodal_contents → content 拼接**（`_join_multimodal_contents`，必须在 title/content 向量化之前）；
  6. title/content 向量化（`.tolist()`）；
  7. **keywords 缺省**：基于 `legacy_gen_keyword_by_title_content`（jieba.analyse.textrank，本地零外部调用）；
  8. 空 indexes 清理；
  9. segment 去 title/synonyms_title；
  10. 时间字段（insert_time 仅新建；update_time 总刷新）；
  11. 新建时 from_type/from_type_norm/tags 缺省（from_type_norm 用 `legacy_get_from_norm_type` 规则映射；tags 缺省=keywords）；
  12. `del_flag=0`（底层引擎存储契约，新建必填）；
  13. category_infos[].category_id 强制 str（primary_category 构造依赖 HTTP，跳过）；
  14. dataset 缺省 = index_name；
  15. `_id = gen_data_id`（仅新建）。
- `_join_multimodal_contents(multimodal_contents)`：与旧 `SearchDataInterface.join_multimodal_contents` 等价；file/image/video/audio 用字面 `[multimodal_prefix]` 占位，由 search_text 阶段替换。
- `_cal_similarity / _cal_title_similarity`：复刻旧实现，复用 `cosine_similarity`。qa：有 title → `title_sim + 0.2*content_sim`，否则 content_sim；非 qa → max；data_type 含 image → 叠加 image_indexes 最大相似度。

## 仍然刻意排除（属重业务，不在 CRUD）
- 去重 dedup（find_duplicates / SimilityTools / Dify LLM）+ is_update_data 软删除
- primary_category 构造（依赖 category_service HTTP）

## 关键依赖
- `kdb.crud.repository.KnowledgeRepository`
- `kdb.embedding.client.EmbeddingClient`（注入）
- `kdb.crud.ids.gen_data_id`、`kdb.legacy_bridge.cosine_similarity`
- `kdb.legacy_bridge.legacy_gen_keyword_by_title_content`（jieba 本地）、`legacy_get_from_norm_type`（规则映射）

## SQL
不读写 SQL。
