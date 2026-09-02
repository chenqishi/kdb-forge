# KnowledgeService

## 所属文件
`src/kdb/crud/service.py`

## 功能描述
文本级 CRUD 层，**旧 `SearchDataInterface` 检索/写入接口的完整替代**。生成向量与 _id、补齐 `process_one_data` 全部业务默认、默认查重、多 query、web 分页检索，委托 `KnowledgeRepository`。注入 `EmbeddingClient` / `SimilityTools`（查重）/ `CategoryClient`（类目映射）。逐行复刻旧 `search_index_data_interface.py`；有意差异见 `docs/CRUD_Legacy_Difference_Issues.md` 第 0/0.1 节（均有离线差分测试契约）。

## 构造
- `__init__(repository, embedding_client, default_index=None, multimodal_prefix="", check_duplicate=True, is_need_llm=False, simility_tools=None, category_client=None)`
  - `multimodal_prefix`：检索返回前替换 content 中 `[multimodal_prefix]` 占位的真实前缀。**空串会把占位符删除**（str.replace 语义，与旧一致），不是"保留不替换"。
  - `check_duplicate`/`is_need_llm`：`insert_data` 未显式传参时的缺省（对齐旧 config）。
  - `simility_tools`：查重工具；None 时懒构造旧 `SimilityTools(None)`（无 LLM），导入失败用内置 `_FallbackSimilityTools`。
  - `category_client`：web_search 的 category_names→ids 映射；None 时无 URL 降级实例。
- `from_config(config_path, index_name=None)`：从 `legacy_search_config_path` 指向的旧 config 装载 multimodal_prefix/check_duplicate/is_need_llm/simility_config_path/category_service_url（与旧同源）；漏配打 warning。索引解析：显式参数 > `default_index_name` > `test_index_name`（**告警**）> engine config（**告警**，不再静默）。

## 方法 Inputs/Outputs

### 新 API
- `insert_text(doc, index_name=None, refresh_imm=False) -> (bool, str)`：最小插入，**无查重**、`_prepare_document` 异常上抛；引擎失败 `(False,"insert failed")`。index_name 兜底 dataset（缺省 default_index）。
- `search_text(query, index_name=None, condition_dicts=None, size=10, search_type='qa', data_type='text', use_synonyms=False) -> (List[Dict], int)`：默认条件 quality_level=['high'] + audit_result=[1,2] 两组、缺省补 [1,2,-1]；`repo.search_multi(size=size*2)`；每 doc 加 similarity + 前缀替换；**不排序不截断**。index 接受 str（逗号分隔）或 List[str]（旧仅 str，安全超集）。
- `search_text_multi(query_list, index_name=None, condition_dicts=None, size=10, ...) -> (List[Dict], int)`：多 query 单请求（query/vector 传 list）；默认条件 audit_result=[1]、缺省补 **[1,-1]**（与单 query 不同）；每 doc similarity 取各 query 最大；**不做前缀替换**（旧如此）；主路径异常回退多线程逐 query（去重合并、按相似度排序、截断 size、total 取最大）。空 query_list → ([],0)。
- `web_search(query, client=None, index_name=None, condition_dicts=None, page_size=None, page_num=1, score_threshold=None) -> (List[Dict], int)`：允许空 query（不 embed）；条件缺省 []；category_names→category_ids（client 缺省取首个索引名，经 CategoryClient，未命中丢弃，与显式 ids 合并）；page_size 缺省 10000；`repo.search_by_page`；返回前前缀替换 + `score=min(score/5.0,1.0)`。
- `find_duplicates(data, topK=5, is_need_llm=True, index_name=None, exclude_self=False, is_only_title=False, basic_threshold=0.7, title_basic_threshold=0.95) -> List[Dict]`：**浅 copy**（与旧一致，含 ext_info 泄漏行为）→ `_prepare_document`（失败→[]）→ title+content 文本 + 首 index 向量 + data_type/platform('unkonw' 旧拼写) 检索 → SimilityTools 判定。
- `batch_insert_data(data_list, check_duplicate=True) -> List[(bool,str)]`（alias `batch_insert`）。
- `update(data_id, doc, index_name=None, regenerate_embedding=False, refresh=False) -> bool`：增强更新（刷新 update_time、可重算向量、可强制 refresh）。
- `delete(data_id, index_name=None, refresh=False) -> bool`；`get(data_id, index_name=None) -> Optional[Dict]`。

### 旧契约替代与 alias
- `insert_data(data, check_duplicate=None, index_name=None, is_update_data=False, is_only_title=False, basic_threshold=0.7, title_basic_threshold=0.95, refresh_imm=False, is_need_llm=None) -> (bool, str)`：check_duplicate=None 取构造缺省；重复→`(False,'数据重复')` 或 is_update_data 软删（`update_by_condition del_flag=1/del_reason=cover_by_new`，known no-op 保留）后插入；`_prepare_document` 异常→`(False,'数据处理失败')`；引擎失败→`(False,'')`。**index_name 不兜底 dataset**（与旧一致）。不复刻旧"调用方 dict 塞 _id=None"副作用。
- `search_data_by_query` / `search_data_by_multi_query` / `web_search_data`（旧参数名 index_names）→ 对应新方法。
- `update_data(data_id, data)`：原样透传（不刷 update_time、默认索引）；`delete_data` / `search_data` / `get_data_by_id` / `update_data_value(index_name, dict, conditions)` / `get_unique_values(index_name, field, ...)`：旧参数顺序透传 repo。

## 内部方法
- `_prepare_document(data, index_name=None) -> Dict`：
  1. 非 schema 字段归入 ext_info（依据 `SCHEMA_FIELDS`）；
  2. `is_audit→audit_result` 迁移；新建时 audit_result/quality_level 缺省与合法性矫正（合法集 {-1,0,1,2} 与旧 si:476 对齐，2=已审核态；2026-09-02 前抄漏 2 曾把 audit=2 的 upsert 静默降 -1）；
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
- primary_category 构造（依赖 category_service 类目链 HTTP，写入路径不构造）
- 去重的 Dify LLM 分支需外部配置（阈值判定已本地可用）

## 关键依赖
- `kdb.crud.repository.KnowledgeRepository`
- `kdb.embedding.client.EmbeddingClient`（注入）
- `kdb.category.client.CategoryClient`（注入，可降级）
- `kdb.legacy_bridge.LegacySimilityTools`（软依赖，内置 `_FallbackSimilityTools` 兜底）
- `kdb.crud.ids.gen_data_id`、`kdb.legacy_bridge.cosine_similarity`
- `kdb.legacy_bridge.legacy_gen_keyword_by_title_content`（jieba 本地；**只吞 ImportError**，运行期异常上抛）、`legacy_get_from_norm_type`（规则映射）

## SQL
不读写 SQL。
