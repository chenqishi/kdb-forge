# 架构总览（rebuild）

> 重构第一步：CRUD 层抽取。后续步骤（pipeline、tasks）将扩展本图。

## 分层

```
┌─────────────────────────────────────────────────────────────┐
│  调用方 / 后续 pipeline / tasks（预留）                       │
└───────────────┬─────────────────────────────────────────────┘
                │ 文本级文档 / query
                ▼
┌─────────────────────────────────────────────────────────────┐
│  kdb.crud.KnowledgeService（文本级 CRUD）                     │
│  - insert_text / search_text / update / delete / get          │
│  - _prepare_document：向量化 + _id + 时间（复刻旧 process_one_data 子集）│
│  - _cal_similarity：相似度重排（复刻旧实现）                   │
│  依赖注入：EmbeddingClient                                     │
└──────┬──────────────────────────────────┬────────────────────┘
       │ 已含向量的文档 / query_dict        │ text2embedding
       ▼                                    ▼
┌──────────────────────────────┐   ┌──────────────────────────┐
│ kdb.crud.KnowledgeRepository │   │ kdb.embedding.client      │
│ （纯向量 CRUD）              │   │  EmbeddingClient 协议      │
│ insert/get/search/search_multi│  │  + AliEmbedding 适配      │
│ /search_by_page/update_by_id  │   └─────────────┬────────────┘
│ /update_by_condition/delete   │                 │
│ /get_unique_values/ensure_index│                │
└──────────────┬────────────────┘                 │
               │ 全部委托                          │
               ▼                                   ▼
┌─────────────────────────────────────────────────────────────┐
│  kdb.legacy_bridge（接线层：sys.path 注入旧项目）            │
│  re-export: EsSearchInterface / AliEmbedding /                │
│             gen_data_id / cosine_similarity                   │
└───────────────┬─────────────────────────────────────────────┘
                │ import 复用（不修改旧代码）
                ▼
┌─────────────────────────────────────────────────────────────┐
│  旧项目 knowledge_database_builder                            │
│  - knowledge_interface_tools/es_search_interface.py           │
│      EsSearchInterface（ES7.x / OpenSearch2.19 双引擎驱动）    │
│      权威 ES mapping（_ensure_index）                         │
│  - commons/embedding_tools.py（AliEmbedding / DashScope）     │
└───────────────┬─────────────────────────────────────────────┘
                ▼
        Elasticsearch / OpenSearch（索引：生产索引 / test_case）
```

## 关键约束

- **Schema 不变**：CRUD 不修改 ES mapping 字段（不删、不改义；可增）。权威定义在旧 `_ensure_index`。
- **CRUD 纯净**：Repository 只进出向量；Service 只做向量化/_id/时间；**不含** 去重、类目映射、关键词、质量过滤、多模态 join——这些属业务逻辑，留给后续 pipeline 模块。
- **对齐基准**：Service 的 `_prepare_document` / `search_text` / `_cal_similarity` 逐行复刻旧
  `search_index_data_interface.py` 的对应逻辑，保证与旧 `SearchDataInterface` 行为对齐。

## 数据流

- **写**：`insert_text(doc)` → `_prepare_document`（归集 ext_info、构造 indexes、向量化、_id、时间）→ `repo.insert` → 旧 `engine.insert`（校验维度/过滤零向量/upsert）→ ES。
- **读**：`search_text(query)` → embed query → `repo.search_multi`（混合检索，候选 size*2）→ 逐 doc `_cal_similarity` → 返回 (docs, total)，不排序不截断。
- **改**：`update`（局部合并 + 刷新 update_time，可选重算向量）/ `repo.update_by_condition`（软删除 del_flag=1 等）。
- **删**：`delete` → 旧 `engine.delete`。
