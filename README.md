# knowledge_database_builder_rebuild

旧项目 `knowledge_database_builder` 的高内聚低耦合重构版。**当前进度：第一步——抽取干净的知识库 CRUD 模块。**

## 设计要点

- **两层 CRUD + 旧接口兼容**：
  - `kdb.crud.KnowledgeRepository`：纯向量 CRUD（insert/get/search/update/delete），封装 ES8.17 路由引擎，不含任何业务逻辑。
  - `kdb.crud.KnowledgeService`：文本级 CRUD，同时原样暴露旧 `insert_data`、`search_data`、`search_data_by_query`、`search_data_by_multi_query`、`web_search_data`、批量插入、查重、类目和文件名操作。
  - `kdb.crud.SearchDataInterface` / `kdb.knowledge_interface_tools.search_index_data_interface.SearchDataInterface`：旧构造函数兼容入口。
- **ES 8.17 原生检索**：生产 CRUD 使用 ES8 named API；BM25/vector 双路中的 vector 路使用 indexed `dense_vector` + native HNSW KNN，不再使用旧 ES7 `body=`/`script_score`。
- **兼容旧基线**：`kdb.legacy_bridge` 仍以 sys.path 注入旧项目，供 `_id`、embedding、关键词、类目默认和对齐测试使用；生产 `RoutedLegacyEngine` 不再调用旧 ES7 client。
- **Schema 可迁移**：字段语义沿用旧 mapping；新索引要求 `indexes.embedding` 为 `index=true, similarity=cosine, index_options.type=hnsw`。旧 ES7 未索引向量索引需新建目标索引并 reindex。
- **业务默认对齐口径**：
  - **已对齐**（纯本地、零外部 IO）：is_audit→audit_result、audit_result/quality_level/from_type 缺省与矫正、from_type_norm（规则映射）、keywords（jieba.analyse 本地分词）、tags=keywords、category_infos[].category_id→str、dataset 缺省=index_name、multimodal_contents→content 拼接、search 返回时 `[multimodal_prefix]` 替换。
  - **兼容服务已补齐**：dedup 去重、primary_category 构造、web_search、批量插入和按文件操作都由兼容层暴露，底层请求统一走 ES8.17。
  - **范围排除**：Payoneer Olive 自动类目推断属于上游挖掘，CRUD/检索不实现；仍支持显式类目入库、通用类目解析和过滤。

## 目录

```
src/kdb/
  legacy_bridge.py     # 接线：路由引擎 + 兼容旧 embedding/_id/AliEmbedding
  es/client_router.py  # index -> Serverless/PaaS -> ES8.17 client
  es/engine.py         # ES8 named API、native KNN、按 provider 拆分多索引请求
  crud/repository.py   # KnowledgeRepository（纯向量）
  crud/service.py      # KnowledgeService（文本级）
  crud/legacy_compat.py# 旧 SearchDataInterface 方法兼容层
  crud/ids.py          # _id 生成（复用旧 gen_data_id，带兜底）
  crud/models.py       # schema 字段集合常量
  embedding/client.py  # EmbeddingClient 协议 + AliEmbedding 适配
  config/loader.py     # 配置加载
  pipeline/ tasks/     # 预留（后续步骤）
tests/                 # 集成测试（真实 ES + DashScope）
config/config_test.json# 引用旧 config 的绝对路径（不提交 git，见 .gitignore）
config/config_es_engine.json.example # ES8.17 单地址/混合路由模板
```

## 配置

复制模板并填入旧 config 的绝对路径（**真实 config 不提交 git**）：

```bash
cp config/config_test.json.example config/config_test.json
# 编辑三个 *_config_path 指向旧项目 config/ 下对应文件
```

## 运行测试

```bash
./run_tests.sh                  # 全部集成测试（建 test_case 索引 → 回环 → 与旧实现对齐）
KDB_LEGACY_ROOT=/path/to/old ./run_tests.sh   # 覆盖旧项目根路径
```

`python3 -m pytest -q -m 'not integration'` 可运行离线路由/业务单测；完整集成测试需要可访问的 ES8.17 与 DashScope embedding 服务，使用配置中的独立测试索引。

混用两个 Aliyun ES 服务时，按 `config/config_es_engine.json.example` 增加 `providers`、
`default_provider` 和 `index_routes`；`pass` 是 `paas` 的兼容别名。

## 已知行为 / 遗留陷阱（实现过程中踩到的，后续 pipeline 作者请避开）

1. **`del_flag=0` 是底层引擎的存储契约，不是业务默认值**。旧 `EsSearchInterface.search_multi/search/search_by_page` 在 attribute 不带 `del_flag` 时强制注入 `{term:del_flag=0}`，缺该字段的文档**默认搜不到**。`KnowledgeService._prepare_document` 在新建时已自动填 `del_flag=0`。
2. **旧 `engine.update_value` 用 `_id` 做 `terms` 过滤是 silent no-op**：ES 要求 `_id` 用 `ids` 查询，`terms:_id` 不抛错但 0 命中，函数仍返回 True。要按 _id 改字段请用 `repository.update_by_id`；要按条件批量请用 `platform` 等其他字段。
3. **Aliyun ES serverless 在高频写后 get/search 有可见延迟**。`KnowledgeRepository.update_by_id / update_by_condition / delete` 在 `refresh=True` 时除 `es.delete/update(refresh=True)` 外还额外调一次 `indices.refresh`；测试代码用 `tests/conftest.py` 的 `wait_for_present / wait_for_absent / wait_for_field / wait_for_search_hit` 轮询替代固定 sleep。
4. **旧 ES7 索引不能直接复用 native KNN**。如果 `indexes.embedding` 的 mapping 缺少 `index:true` 或维度不符，ES8 引擎会明确拒绝启动；必须创建新索引、使用新 mapping，然后 reindex。这样可以避免误以为“客户端升级了”就已经启用向量索引。
5. **多 shard ES 在两个不同 `EsSearchInterface` 实例下查同一份数据，分数极接近时 raw 结果顺序可能微抖动**。对齐口径：①命中 `_id` 集合相同；②每个 _id 的 `similarity` 在 `1e-6` 容差内一致；③按 `similarity` 降序排序后顺序完全一致（见 `test_alignment_with_legacy.py`）。
6. **`legacy_bridge` 通过 sys.path 注入旧项目根**（环境变量 `KDB_LEGACY_ROOT` 可覆盖）。`gen_data_id` 走旧 import 链可能稍慢（实测约 1.4s 一次性 import）；不可用时 `ids.py` 内置字节级一致的复刻兜底（`md5(f"{title}_{content}_{data_type}")`）。
