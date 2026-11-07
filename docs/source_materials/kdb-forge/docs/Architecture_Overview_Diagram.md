# 架构总览（rebuild）

> 重构第一步：CRUD 层抽取。后续步骤（pipeline、tasks）将扩展本图。

## 分层

```
┌─────────────────────────────────────────────────────────────┐
│  调用方 / sell_agent / 后续 pipeline / tasks（预留）           │
└───────────────┬─────────────────────────────────────────────┘
                │ 文本级文档 / query，或 HTTP 写入请求
                ▼
┌─────────────────────────────────────────────────────────────┐
│  kdb.api：health / knowledge insert / delete / modify         │
│  kdb.modify：执行已决策的单索引写入计划；dry_run 不加载 CRUD    │
│  包级公开 CRUD 类懒导入；首次实际写入才构建 Service            │
└───────────────┬─────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────┐
│  kdb.crud.KnowledgeService（文本级 CRUD + 旧接口兼容）          │
│  - 新式：insert_text / search_text / update / delete / get      │
│  - 旧式：insert_data / search_data / web_search_data / ...      │
│  - 新增别名：search_text_multi / web_search / batch_insert      │
│  - _prepare_document：CRUD 预处理，不含客户专属挖掘推断         │
│  - _cal_similarity：相似度重排（复刻旧实现）                    │
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
│  kdb.legacy_bridge（接线层：旧项目仅用于兼容/对齐测试）       │
│  RoutedLegacyEngine（ES8 named API + native KNN）             │
│  + re-export: AliEmbedding / gen_data_id / cosine_similarity  │
└───────────────┬─────────────────────────────────────────────┘
                │ 仅 embedding、_id、对齐基线按需 import
                ▼
┌─────────────────────────────────────────────────────────────┐
│  兼容入口 kdb.knowledge_interface_tools                         │
│  - SearchDataInterface：保留旧构造函数和公开方法名              │
│  - 旧调用方无需改 insert/search/web_search 方法名               │
│  - commons/embedding_tools.py（AliEmbedding / DashScope）     │
└───────────────┬─────────────────────────────────────────────┘
                ▼
┌──────────────────────────┐    ┌────────────────────────────┐
│ IndexClientRouter         │───▶│ ES 8.17 Serverless client   │
│ index -> provider ->      │    └──────────────┬─────────────┘
│ cached client             │                   │
│ exact > wildcard > default│    ┌──────────────▼─────────────┐
│                           │───▶│ ES 8.17 PaaS client         │
└──────────────────────────┘    └──────────────┬─────────────┘
                                               ▼
                                Aliyun Elasticsearch（混用）
```

检索时 `RoutedLegacyEngine.search_multi` 使用 ES8 named `search(query=...)`，把 BM25 和
native KNN 分成两路召回，按 `_index + _id` 合并；`search_multi_by_page` 使用 named
`from_` 保持 BM25 分页路径。每个 index 通过 `IndexClientRouter` 交给正确的 ES8.17
Serverless/PaaS client，跨 provider 的多索引请求按 provider 拆分。

## 关键约束

- **ES8 专用**：运行目标只有 ES8.17.x；`Legacy` 类名、方法和配置兼容不意味着支持
  ES7 服务端。合并远端写入功能时不得恢复 ES7 驱动或 script_score 模拟召回。
- **Schema 不变且可迁移**：字段语义沿用旧 mapping，但新索引的 `indexes.embedding` 必须是
  `index=true`、`similarity=cosine`、HNSW。旧 ES7 未索引向量不可原地改 mapping，必须新建
  ES8 索引并 reindex。
- **分层但不丢接口**：Repository 只进出向量；Service/兼容层负责旧 `SearchDataInterface`
  的 CRUD/检索公开契约，包括查重、通用类目、文件名操作、批量插入和 web_search。
- **挖掘边界**：Payoneer Olive 自动类目推断属于上游挖掘，不迁入 CRUD/检索层。
  CRUD 仅规范化、解析显式类目并补默认分组，不按平台线索、标签、标题猜类目；
  类目树不可用时保留上游候选，不按 `source` 丢弃。`web_search` 的类目名转 ID 过滤保留。
- **对齐基准**：旧方法名和返回结构保持不变；底层请求统一改为 ES8 named API，向量路由改为
  native KNN。旧 ES7 索引仍需先迁移到 native KNN mapping。
- **HTTP 契约**：`/search`、`/web_search` 复用旧请求/返回结构并加独立 HTTP Basic；
  `/knowledge/insert`、`/knowledge/delete`、`/knowledge/modify_direct_update` 保持写入接口；
  旧 HTTP 11 路由的管理路径在 `legacy_routes` 兼容层恢复，Dify 修改路径仅在注入外部 modifier 时执行。
- **依赖注入**：远端 similarity/category 注入参数保留；通用类目映射复用兼容层，
  不引入缺失的 CategoryClient 包；查重工具缺失时懒加载本地阈值实现，不跳过查重。

## 数据流

- **写**：`insert_text(doc)` → `_prepare_document`（归集 ext_info、构造 indexes、向量化、_id、时间）→ `repo.insert` → ES8 `RoutedLegacyEngine.insert`（校验维度/过滤零向量/upsert）→ ES。
- **读**：`search_text(query)` → embed query → `repo.search_multi`（BM25/vector 双路，候选 size*2）→ 逐 doc `_cal_similarity` → 渲染多模态 URL → 返回 (docs, total)，不排序不截断。
- **改**：`update` → title/synonyms 变更且未显式提供 indexes 时，通过同一 index 的
  `repo.get` 读取原文档 → 合并派生检索项并保留其他项 → 重算 root/indexes 向量 →
  `repo.update_by_id` → 按目标 index 刷新；读不到原文档则拒绝该合并写入。
  content-only 更新不额外读库；`repo.update_by_condition` 用于软删除 del_flag=1 等。
- **删**：`delete` → ES8 `RoutedLegacyEngine.delete`。
- **兼容**：`SearchDataInterface(config_path=..., index_name=...)` → `KnowledgeService` 兼容层；
  `web_search_data` → ES8 BM25 分页 + 类目 ID 转换 + URL/score 后处理；文件名删除使用
  ES8 `count/search/agg_terms/update_by_query`，删前写 JSONL 快照。
