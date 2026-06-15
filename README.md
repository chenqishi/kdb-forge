# knowledge_database_builder_rebuild

旧项目 `knowledge_database_builder` 的高内聚低耦合重构版。**当前进度：第一步——抽取干净的知识库 CRUD 模块。**

## 设计要点

- **两层 CRUD**：
  - `kdb.crud.KnowledgeRepository`：纯向量 CRUD（insert/get/search/update/delete），封装并复用旧 `EsSearchInterface`，不含任何业务逻辑。
  - `kdb.crud.KnowledgeService`：文本级 CRUD（insert_text/search_text/update/delete），注入 `EmbeddingClient`，负责向量化、_id 生成、时间字段，并补齐旧 `process_one_data` 中**纯本地、零外部 IO** 的业务默认（详见下方"业务默认对齐口径"与 `docs/CRUD_Legacy_Difference_Issues.md`）。
- **复用旧底层**：通过 `kdb.legacy_bridge` 以 sys.path 注入方式复用旧 `EsSearchInterface` 与 `AliEmbedding`，不重写、不修改旧代码。
- **Schema 不变**：沿用旧权威 ES mapping（不删字段、不改字段含义；新增字段允许）。
- **业务默认对齐口径**：
  - **已对齐**（纯本地、零外部 IO）：is_audit→audit_result、audit_result/quality_level/from_type 缺省与矫正、from_type_norm（规则映射）、keywords（jieba.analyse 本地分词）、tags=keywords、category_infos[].category_id→str、dataset 缺省=index_name、multimodal_contents→content 拼接、search 返回时 `[multimodal_prefix]` 替换。
  - **仍刻意排除**（依赖外部 HTTP/LLM）：dedup 去重（Dify LLM+SimilityTools）、primary_category 构造（category_service HTTP）——留给后续 pipeline。

## 目录

```
src/kdb/
  legacy_bridge.py     # 接线：复用旧 EsSearchInterface / AliEmbedding / gen_data_id / cosine_similarity
  crud/repository.py   # KnowledgeRepository（纯向量）
  crud/service.py      # KnowledgeService（文本级）
  crud/ids.py          # _id 生成（复用旧 gen_data_id，带兜底）
  crud/models.py       # schema 字段集合常量
  embedding/client.py  # EmbeddingClient 协议 + AliEmbedding 适配
  config/loader.py     # 配置加载
  pipeline/ tasks/     # 预留（后续步骤）
tests/                 # 集成测试（真实 ES + DashScope）
config/config_test.json# 引用旧 config 的绝对路径（不提交 git，见 .gitignore）
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

测试为**集成测试**，需要可访问的 ES/OpenSearch 与 DashScope embedding 服务，使用独立索引 `test_case`。

## 已知行为 / 遗留陷阱（实现过程中踩到的，后续 pipeline 作者请避开）

1. **`del_flag=0` 是底层引擎的存储契约，不是业务默认值**。旧 `EsSearchInterface.search_multi/search/search_by_page` 在 attribute 不带 `del_flag` 时强制注入 `{term:del_flag=0}`，缺该字段的文档**默认搜不到**。`KnowledgeService._prepare_document` 在新建时已自动填 `del_flag=0`。
2. **旧 `engine.update_value` 用 `_id` 做 `terms` 过滤是 silent no-op**：ES 要求 `_id` 用 `ids` 查询，`terms:_id` 不抛错但 0 命中，函数仍返回 True。要按 _id 改字段请用 `repository.update_by_id`；要按条件批量请用 `platform` 等其他字段。
3. **Aliyun ES serverless 在高频写后 get/search 有可见延迟**。`KnowledgeRepository.update_by_id / update_by_condition / delete` 在 `refresh=True` 时除 `es.delete/update(refresh=True)` 外还额外调一次 `indices.refresh`；测试代码用 `tests/conftest.py` 的 `wait_for_present / wait_for_absent / wait_for_field / wait_for_search_hit` 轮询替代固定 sleep。
4. **`test_case` 索引首次创建时 serverless 会丢掉 `indexes.embedding` 上的 `similarity:cosine` 参数**（dense_vector 默认 `index:false` 时它无效）。结果是后续 `update_index_map` 检测 mismatch 抛 `ValueError`，被旧代码 try/except 吞掉、只记录 ERROR 日志，**非致命**——CRUD 检索用 script_score 计算 cosine 不依赖该参数。
5. **多 shard ES 在两个不同 `EsSearchInterface` 实例下查同一份数据，分数极接近时 raw 结果顺序可能微抖动**。对齐口径：①命中 `_id` 集合相同；②每个 _id 的 `similarity` 在 `1e-6` 容差内一致；③按 `similarity` 降序排序后顺序完全一致（见 `test_alignment_with_legacy.py`）。
6. **`legacy_bridge` 通过 sys.path 注入旧项目根**（环境变量 `KDB_LEGACY_ROOT` 可覆盖）。`gen_data_id` 走旧 import 链可能稍慢（实测约 1.4s 一次性 import）；不可用时 `ids.py` 内置字节级一致的复刻兜底（`md5(f"{title}_{content}_{data_type}")`）。
