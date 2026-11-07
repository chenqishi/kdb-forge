# ES8.17 引擎替代审核报告（EsSearchInterfaceES8）

- 审核日期：2026-10-02
- 审核对象：`knowledge_interface_tools/es8_search_interface.py`、`knowledge_interface_tools/es8_client_router.py`、`knowledge_interface_tools/es_search_interface.py`（旧引擎与工厂）、`knowledge_interface_tools/search_index_data_interface.py`（上层调用）、配置示例、`tests/test_es8_interface.py`、`function_schema/`
- 基准提交：`a36efc72`（main，HEAD，工作区另有未提交改动：`MEMORY.md` 修改及大量未跟踪 config/tmp/docs 文件）。ES8 相关提交：`a00c4a62`（feat: isolated ES8.17 routed engine）、`a36efc72`（fix: nested knn inner hits）。分支 `codex/es817-old-engine` 指向 `a00c4a62`。
- 审核方式：先独立静态比对旧 `EsSearchInterfaceOri` 与新 `EsSearchInterfaceES8`（逐方法），再做离线 fake-client 差分复现（`tmp/es8_audit_diff.py`），再对真实 ES8.17 集群做只读验证（`tmp/es8_audit_readonly.py`、`tmp/es8_audit_real_ro.py`），最后对照既有审核材料（kdb-forge 的 `ES8_Retrieval_Migration_Plan.md`、`ES8_Index_Routing.md`、`feedback_es8_only.md`、`Merge_ES8_Write_API.md`、`MEMORY.md`）。
- 环境事实：真实 runtime 配置 `/root/kdb-forge/config/config_es_runtime.local.json`（`es_version: "8.17"`，serverless+paas 双 provider，`index_routes: {"payoneer*","*payoneer*"} -> paas`）；ES8 运行时 `/root/kdb-forge/.venv-es817`（elasticsearch 8.17.2）；旧集群（config_es_engine.json 指向）为阿里云 serverless ES 7.10.0。**本次未执行任何写操作**（未创建/删除/重建索引、未写文档、未改 mapping、未重启服务）。

---

## 0. 结论（先回答核心问题）

**当前状态不能仅通过修改配置就用 ES8.17 引擎替换旧引擎。** 前提还需满足：业务索引已完成「新建 HNSW mapping + reindex」迁移（旧 ES7 索引会被 ES8 守卫 fail-closed 拒绝），且服务必须运行在 elasticsearch 8.17 的独立运行时（与旧 7.10 client 互斥，实测混用 406）。即使迁移完成，仍有 3 个阻断性缺陷必须先修：

1. **`search_after` 在新引擎完全不可用**（死代码恒空 + ES8.17 对 `sort: _id` 直接 400），属于公开接口契约破坏。
2. **`agg_terms` 返回结构不兼容**：上层 `list_file_names` 的类型分布 `type_count` 静默恒为空。
3. **仓库自带示例配置 `config_es_engine_es817.example.json` 无法通过工厂初始化**（`es_version: "es8.17"` 不满足实现的 `startswith("8.17")` 校验）。

另有若干需业务确认的行为差异（异常语义、noop/not_found 返回值、多索引 dual 的 total 口径、web_search 大页无拆批、`auto_update_mapping` 被忽略等），详见下文。

---

## 1. 问题清单（按严重程度）

### 阻断级

#### P1. `search_after` 完全失效：恒空 + ES8.17 上默认排序字段非法（新增错误 + 升级必要变化）

- 位置：
  - `knowledge_interface_tools/es8_search_interface.py:946-963`（`search_after`）——`if not hits: break` 后紧跟的 `yield from self._hits(response)`（行 958）是**不可达死代码**，任何情况下该方法都一个文档不产出。
  - 同方法行 954 `sort=[{sort_field: "asc"}]`，默认 `sort_field="_id"`。
- 旧行为：`es_search_interface.py:1999-2164` 逐批 `yield {"_id","score",**source}`，排序 `{_id: asc}`。
- 新行为：① 迭代器恒空（mock 差分复现：旧 2 条 vs 新 0 条，且新引擎确实发起了 2 次 search）；② 真实 ES8.17 集群（serverless）验证：即便去掉死代码，`sort: _id` 也被服务端拒绝——`BadRequestError(400, 'search_phase_execution_exception', 'Fielddata access on the _id field is disallowed...')`。
- 触发条件：任何 `search_after` 调用。仓库内当前无直接调用方（`data_control_tools/data_transfer_tools.py` 用 `scroll_search`；`commons/es_http_client.py` 自带实现），但这是旧引擎公开接口，属契约破坏；且它是备用迁移/审计类脚本的常见依赖。
- 影响：静默返回空迭代，调用方会误判「库里没有数据」。
- 证据：`tmp/es8_audit_diff.py` 第 B 节（mock 差分）；`tmp/es8_audit_real_ro.py` 第 7 节（真实 400）。
- 分类：新增错误（死代码）+ ES8 升级必要变化（`_id` 排序在 ES8.17 被禁用，需换 `_shard_doc`/`insert_time+_id` tiebreaker 等排序键）。

#### P2. `agg_terms` 返回结构不兼容，`list_file_names` 的类型分布静默丢失（兼容性回归）

- 位置：`knowledge_interface_tools/es8_search_interface.py:1044-1053` 直接返回原始 buckets；旧实现 `es_search_interface.py:412-433` 返回转换后的 `[{key, doc_count, sub: {聚合名: {key: count}}}]`。
- 上层消费：`search_index_data_interface.py:927-933`（`list_file_names`）读 `b["key"]`、`b["doc_count"]`、`b.get("sub")["by_type"]`；新返回的 bucket 里没有 `sub` 键，`by_type` 是 ES 原始子聚合结构 → `type_count` **恒为 `{}`**，前端「按来源文件名看类型分布」功能静默失效。
- 其他调用方核对：`resolve_file_name`（935-1011，用 `b["key"]/b["doc_count"]`）、`preview_delete_by_file`（1034-1037，用 `b["key"]/b["doc_count"]`）恰好能用原始 bucket 正常工作，不受影响。
- 证据：mock 差分（`tmp/es8_audit_diff.py` 第 A 节）：旧 `{"sub": {"by_type": {"qa": 3, "doc": 2}}}` vs 新 `{"by_type": {"buckets": [...]}}`；真实集群验证（`tmp/es8_audit_real_ro.py` 第 6 节）：真实返回条目均无 `sub` 键。`tests/test_es8_interface.py` 没有覆盖 `agg_terms`，`function_schema` 文档也未记录旧返回契约。
- 分类：兼容性回归（新实现未适配旧返回契约）。

#### P3. 仓库自带示例配置无法通过工厂初始化（新增错误）

- 位置：`config/config_es_engine_es817.example.json:2` 写 `"es_version": "es8.17"`；`es8_search_interface.py:112-114` 校验 `if not self.es_version.startswith("8.17"): raise ValueError`。工厂 `es_search_interface.py:3507` 只对 `es8`/`elasticsearch8`/`8.` 前缀做归一化并把 `es_version` 改写为 `'es8.17'`，但**原样透传 `config_path`**，ES8 实现会重新读文件，读到 `"es8.17"` 后 `startswith("8.17")` 为 False。
- 复现：`EsSearchInterface(config_path="config/config_es_engine_es817.example.json")` → `ValueError: 重构版要求 Elasticsearch 8.17.x，当前配置为 'es8.17'`（venv-es817 实测）。
- 对比：真实 runtime 配置用 `"es_version": "8.17"`，工厂链路 `EsSearchInterface → EsSearchInterfaceES8 → IndexClientRouter(serverless+paas)` 初始化成功（venv-es817 实测，无网络依赖）。
- 影响：按仓库文档照抄示例配置的用户第一步就会失败；真实配置可绕过，说明是示例与实现校验不一致。
- 分类：新增错误。

### 高（行为差异，需要业务确认/修复）

#### P4. 热路径异常语义：旧引擎「失败返回空/部分结果」，新引擎「异常上抛」（兼容性回归）

- 位置：旧 `search`（es_search_interface.py:760-764）、`search_multi`（1438-1442）、`search_multi_by_page`（1792-1796）、`get_unique_values`（2273-2276）均捕获一切异常返回 `[]`/`([], 0)`；分片取消重试失败后旧 `_msearch_with_shard_check`/`_single_search_with_retry` 也只是打日志返回部分结果（1489-1491）。
- 新实现：`search`/`search_multi`/`search_multi_by_page`/`search_by_vector`/`get_unique_values`/`get_field_statistics` 均无兜底；`_search_request`（es8_search_interface.py:547-559）重试 3 次后 `raise RuntimeError`；client 的 4xx/5xx/连接错误直接上抛。
- 证据：
  - mock 差分（`tmp/es8_audit_diff.py` 第 D 节）：旧 `search` 抛错时返回 `[]`；新 `search`/`search_multi` 分片失败×3 抛 `RuntimeError`。
  - 真实集群：`engine.search(..., index_names="no_such_index_abc")` 抛 `NotFoundError(404, index_not_found_exception)`（旧引擎同场景返回 `[]`）。
- 上层影响链：`search_data_by_query`/`web_search_data` 不捕获（search_index_data_interface.py:1151、1351）；服务层 `/search`、`/web_search` 路由有 3 次重试兜底，最终返回「检索结果错误」（knowledge_database_search_es.py:364-455、659-712）。也就是说：旧引擎在 ES 分片持续异常时仍能带着部分召回继续作答，新引擎会让整条 `/search` 失败。
- 分类：兼容性回归（旧实现「线上主路宁可结果不完整也不中断」的设计被打破）。

#### P5. web_search 默认 `page_size=10000` 失去旧引擎的拆批保护（兼容性回归，风险项）

- 位置：旧 `_search_with_shard_check` 对 `size > _SAFE_PAGE_BATCH(500)` 逐批 500 重试合并（es_search_interface.py:1515-1539，注释记录了旧 serverless 集群 size≥5000 必败的实测）；新 `search_multi_by_page`（es8_search_interface.py:893-920）经 `_search_request` **单请求直发** size=10000。上层 `web_search_data` 默认 page_size=10000（search_index_data_interface.py:1349-1350）。
- 证据：mock 差分（`tmp/es8_audit_diff.py` 第 C 节）：旧 20 批×500 vs 新单批 10000。真实只读探测：新 serverless 小索引 size=10000 0.2s 成功；PaaS `payoneer_olive__v817_initial_20260930`（根文档 6 万级）size=10000 2.9s 成功——**新集群本次未复现旧集群的取消现象**，但新引擎没有旧引擎的抗取消拆批+重试机制，大索引高负载下的行为未验证。
- 分类：兼容性回归（保护性机制缺失）；严重度取决于新集群负载特性，需压测确认。

### 中

#### P6. `search` 的向量路固定 `k=10`，size>10 时向量候选被截断（ES8 必要变化，参数未跟随 size）

- 位置：`es8_search_interface.py:467` `vector_k: int = 10`，`search`（741-748）不传 `vector_k=size`；`_build_knn_clause` 的 `num_candidates=max(k, max(100, k*10))`（433）。
- 旧行为：`search` 用 `nested+script_score+match_all` 全量暴力打分，size 多大都匹配（es_search_interface.py:715-728）。
- 新行为：native KNN 只回 top-k=10 → `search(..., size=20)` 最多 10 条向量路候选（BM25 路不受限）。mock 差分（第 H 节）已证实请求体 `"k": 10`。
- 仓库内主要调用方 `find_duplicates`（topK=5）不受影响；其余 `search` 调用方若 size>10 且依赖向量召回会静默少召回。
- 分类：ES8 升级必要变化（native KNN 必须给 k），但 k 未跟随 size 是实现欠缺。

#### P7. 多索引 dual 检索的 total 口径变化（兼容性回归）

- 位置：旧 `search_multi` 对每个 msearch 子请求做 `max(total_num, sub_total)`（es_search_interface.py:1399-1400），即**所有子请求取最大值**；新 `_search_multi_group` 按路由累加后组内取 max（es8_search_interface.py:840、873），`search_multi` 跨 provider 再求和（890）。
- 证据：mock 差分（第 G 节）：bm25 两索引 total 40/10、vector 20/30 → 旧 total=40，新 total=50。真实跨 provider 检索 total=42（两索引各 10 条候选）。
- 影响：`/search` 返回给前端的 total_num 口径变化（新口径通常 ≥ 旧口径），分页/「共 N 条」展示可能不一致。
- 分类：兼容性回归（统计口径）。

#### P8. CRUD 返回值语义放宽：noop / not_found 由 False 变 True（兼容性回归）

- 位置：新 `insert`（es8_search_interface.py:680）接受 `{"created","updated","noop"}`；`update`（694）接受 `{"updated","noop"}`；`delete`（703）接受 `{"deleted","not_found"}`。
- 旧行为：`insert`/`update` 只认 `created/updated`，`delete` 只认 `deleted`，其余（含 noop/not_found）返回 False（es_search_interface.py:954、975、999）。
- 证据：mock 差分（第 E 节）：旧 `insert(noop)=False / update(noop)=False / delete(not_found)=False`，新全为 True。
- 影响：`delete_data` 等上层用 bool 判断成功；「删除不存在的文档」现在报告成功（可论证为修正旧引擎 bug——旧实现把幂等操作当失败），但语义变化需业务确认。
- 分类：兼容性回归（返回语义）。

#### P9. `scroll_search` 静默丢弃 vector 检索（兼容性回归，能力收缩）

- 位置：新 `scroll_search` 固定 `include_vector=False`（es8_search_interface.py:928）；旧 scroll 带 `vector` 时构造 `nested+script_score` 子句（es_search_interface.py:1924-1945）。
- 证据：mock 差分（第 F 节）：旧请求体含 script_score，新请求体无 knn。
- 影响：仓库内唯一调用方 `data_transfer_tools.scroll_search(query={}, ...)` 传空 query，不受影响；若外部脚本用 vector+scroll 做语义迁移/审计会静默退化为 BM25-only。应显式报错或文档化，而非静默忽略。
- 分类：兼容性回归（静默能力收缩；换 native KNN 后 scroll 深翻页本身也有语义限制）。

#### P10. dual 模式不再裁剪 `_source` 向量字段（性能回归，正确性反而更完整）

- 位置：旧 dual 用 `_LEAN_SOURCE_EXCLUDES`（indexes/image_indexes.embedding）+ nested inner_hits 补回（es_search_interface.py:35、73、1313-1335）；新 `search_multi`/`search` 不设 `source_excludes`，返回**完整 _source**（含全部 4 个向量字段）。
- 实测：PaaS `payoneer_olive__v817_initial_20260930` dual size=10 墙钟 4.2s、序列化体积 **2.26MB/10 条**（约 226KB/条）。旧实现的注释记录单条 _source 139803 字节中 97.5% 是向量。
- 影响：回传体积回到优化前量级（旧优化从 13.9MB→9.3MB 的收益失效且更差）；但本地重排拿到的 indexes[].embedding 更全（旧有 0.1% 同义问法掉分的已知代价消失）。
- 分类：兼容性回归（性能层面）+ 正确性改善，建议权衡后恢复 lean+inner_hits。

#### P11. `auto_update_mapping` 配置被静默忽略（兼容性回归）

- 位置：新引擎读取并存了 `auto_update_mapping`（es8_search_interface.py:110）但之后从未使用；`update_index_map`（295-308）定义了但**没有任何调用点**；`_ensure_index` 只做向量 mapping 守卫（246-293），不再 diff+put_mapping 补新字段。
- 旧行为：`_ensure_index` 对已存在索引调用 `update_index_map`，`auto_update_mapping=True` 时 put_mapping 补缺失字段（es_search_interface.py:326-328、376-392）。
- 影响：依赖该开关给存量索引补字段的流程在新引擎下失效（`supply_missing_field.py` 自带 client 不受影响）。仓库内 `update_index_map` 的调用方只有 `tests/test_es_mapping_compare.py`（测的是旧引擎）。
- 分类：兼容性回归（配置项失效，应删除配置项或实现等价行为并告警）。

### 低 / 说明

#### P12. 旧 ES7 索引 fail-closed 拒绝 + 双运行时约束（ES8 升级必要变化，已文档化）

- `_ensure_index` 对已存在索引校验 4 个向量字段必须是 `dense_vector + index=true + dims 匹配 + similarity=cosine + index_options.type=hnsw`，否则 RuntimeError（es8_search_interface.py:267-293）。**这是设计意图**（旧 ES7 `indexes.embedding` 无 index 的索引不能原地升级，需重建+reindex；MEMORY.md:120 与 kdb-forge 迁移计划一致），但意味着「仅改配置切换」的前提是索引已迁移。
- 守卫默认 `ensure_index=True`，但仓库示例与真实 runtime 配置都显式 `ensure_index_on_init=false` → 守卫实际被关闭（fail-open）；且 `_group_indexes` 只为每组第一个索引调 `_impl_for`，多索引请求时同组其余索引不会被守卫覆盖（es8_search_interface.py:142-148）。
- 实测：router 拒绝非 8.17.x client（es8_client_router.py:214-223）；旧扁平配置在 8.17 client 运行时下工厂仍会构建 `EsSearchInterfaceOri`（自动检测返回 es7），初始化成功但真实搜索被旧 ES7.10 集群以 `406 Content-Type compatible-with=8 not supported` 拒绝（venv-es817 实测）→ 新旧引擎必须分 venv 部署（`requirements-es8.txt` 已声明）。
- 分类：ES8 升级必要变化（迁移前提 + 部署约束）。

#### P13. `search_by_vector` 的 k、分数量纲变化（ES8 必要变化）

- 旧：k 恒为 10（es_search_interface.py:830、846），size>10 时最多 10 条；新：`k=max(1,size)`（es8_search_interface.py:814）。旧 `cosineSimilarity` 分数量纲 ∈[-1,1]，新 native KNN cosine 分数 = 1+cosine（真实集群实测 1.55 左右）。
- 影响：仓库内无业务调用方（grep 无调用）；外部脚本若依赖 min_score 阈值或分数区间需适配。`min_score` 与 kNN 同用时 ES 官方语义是不对 kNN 生效，未验证。
- 分类：ES8 升级必要变化。

#### P14. 其余小差异

- 新 `search_multi` 对非法 `recall_mode` 抛 ValueError（旧静默按单路处理）；`search_multi` 的 `page_num` 参数新旧都忽略（一致）。
- 新 `get` 对多索引逐索引查找返回首个命中（旧用 `get(index="a,b")` 单请求，逗号串语义未验证）；新 `delete/update/insert` 对多索引**逐索引执行**（旧 `update(index="a,b")` 会被 ES 400 拒绝）。
- 新 `update_value` 以 `failures` 非空判定失败并加 `conflicts=proceed`（旧仅异常判定）；`_id` 条件由旧 `terms._id` 改为 `ids` 查询（两者均有效）。
- 新 `search_multi` 单索引结果新增 `_index` 键（旧单索引路径没有）——超集，`/search` 的 dataset 兜底更稳。
- 新 `insert_with_vectors` 不再校验向量字段名是否在 `vector_fields`（只校验维度）；对单字段配置无差异。
- 旧 `search` 的 except 分支引用未定义的 `final_query`（es_search_interface.py:762）——**旧版已有问题**。
- `knowledge_interface_tools/update_del_flag_batch.py` 调用的 `check_del_flag_coverage`/`update_missing_del_flag` 在旧/新引擎都不存在——**旧版已有问题**，与本次替换无关。

---

## 2. 旧方法与新方法对应表

| 旧 `EsSearchInterfaceOri` 方法 | 新 `EsSearchInterfaceES8` | 结论 |
|---|---|---|
| `__init__`（7.x client、http_auth、auto 建索引） | `__init__`（路由 + 8.17 client、守卫可选） | 行为变化（设计内）：路由、es_version 校验、ensure 开关 |
| `_ensure_index` | `_ensure_index` | 行为变化：新只守卫向量 mapping（fail-closed），不再补字段（P12） |
| `update_index_map` | `update_index_map` | 实现存在但**无调用点**（死代码），语义也改为直接 put_mapping（P11） |
| `count_by_query` | `count_by_query` | 完整实现（+分片重试）；异常语义基本一致 |
| `agg_terms` | `agg_terms` | **返回结构不兼容**（P2） |
| `sample_by_query` | `sample_by_query` | 完整实现（等价） |
| `update_by_query` | `update_by_query` | 完整实现（等价 + 多索引分组求和） |
| `update_value` | `update_value` | 完整实现；小差异：failures 判定、conflicts=proceed、`_id`→ids 查询 |
| `insert_with_vectors` | `insert_with_vectors` | 完整实现；字段名校验放宽（仅维度校验） |
| `_get_index_name` | `_get_index_name` | 等价（规整 + 分组守卫） |
| `search` | `search` | 基本等价；差异：异常上抛（P4）、knn k=10 截断（P6）、无 function_score 包装（分数等价） |
| `search_by_vector` | `search_by_vector` | 完整实现；差异：k=size、分数量纲 1+cosine（P13）、异常上抛 |
| `insert` | `insert` | 基本等价；差异：noop→True（P8）、多索引逐索引写入（旧单请求会失败） |
| `update` | `update` | 基本等价；差异：noop→True（P8）、dotted 字段转嵌套（新） |
| `delete` | `delete` | 基本等价；差异：not_found→True（P8）、多索引逐索引执行 |
| `get` | `get` | 等价（多索引逐索引查找，未找到 None） |
| `_build_es_query` | `_build_es_query` | 等价（fields 分支 + 新 bool DSL） |
| `_build_nested_vector_clause` | `_build_nested_vector_clause` | 签名兼容但**忽略 boost/score_mode/with_inner_hits**，返回 native KNN（内部方法，影响小） |
| `_restore_inner_embeddings` / `_merge_index_embeddings` | 同名 | 等价（inner_hits 名一致 "best_index"） |
| `search_multi` | `search_multi` | 基本等价（legacy→single 映射，新增 bm25/vector 模式）；差异：异常上抛（P4）、多索引 total 口径（P7）、不再 lean source（P10） |
| `_single_search_with_retry` / `_msearch_with_shard_check` / `_search_with_shard_check` / `_search_once_with_retry` | 同名兼容包装 | 差异：旧重试失败后返回部分结果，新重试失败后抛 RuntimeError（P4） |
| `search_multi_by_page` | `search_multi_by_page` | 基本等价（BM25-only、向量维度照旧校验、min_score 条件一致、多索引 offset 消耗一致）；差异：无拆批（P5）、异常上抛（P4） |
| `scroll_search` | `scroll_search` | 基本等价；差异：**静默丢 vector**（P9） |
| `search_after` | `search_after` | **不可用**（P1：死代码恒空 + ES8.17 `_id` 排序 400） |
| `get_unique_values` | `get_unique_values` | 等价 + 多索引去重（新增）；差异：异常上抛 |
| `get_field_statistics` | `get_field_statistics` | 等价；差异：异常上抛（旧返回 error dict） |
| （工厂 `EsSearchInterface`） | es_version 分支新增 es8→ES8 实现 | 默认分支（旧 Ori/Open）不变；`__getattr__` 委托不变；**示例配置链路断**（P3） |

上层（`search_index_data_interface.py`）调用核对结论：`insert`(kw: index_names/refresh_imm)、`update`(data_id, data)、`delete`(kw: index_names/refresh)、`get`(data_id)、`search`(query, size, kw: index_names)、`search_multi`(kw: index_names/size)、`search_multi_by_page`(kw)、`update_value`(位置参数)、`update_by_query`(index_name, query, update_fields)、`count_by_query`、`agg_terms`(含 sub_aggs)、`sample_by_query`、`get_unique_values`(位置参数)、`_search_with_shard_check`(index_name, body) 全部可解析，**签名层面无需改动上层代码**；但 P2/P4/P5/P7/P8 属于「能调通但消费结果变味」的问题。

---

## 3. 路由完整性核对（审核重点 5）

- **按 provider 分组**：`_group_indexes`（es8_search_interface.py:142-148）把逗号/列表索引按 `resolve_provider` 分组，读写入口（insert/update/delete/get/search/search_multi/search_multi_by_page/scroll/search_after/search_by_vector/get_unique_values/update_value/update_by_query）都走分组或 `get_client_by_index`。✓
- **精确 > 通配 > 默认**：`resolve_provider`（es8_client_router.py:173-194）精确规则优先，通配按配置顺序 fnmatch，未命中用 default_provider；真实配置 `*payoneer* -> paas` 与迁移后索引名（`payoneer__v817_*` 等在 PaaS、`individual_20__v817_*` 等在 serverless）吻合，真实只读验证：`payoneer__v817_initial_20260930 → paas`、`individual_20__v817_initial_20260930 → serverless`。✓
- **跨 provider 多索引**：真实只读验证 `search_multi(index_names=[serverless 索引, paas 索引])` 两客户端各查各的（各 10 条、来源索引分布正确），无漏查/串查。✓
- **缓存**：client 按 provider 缓存（一个连接池）；`_impls` 按 index 缓存 binding；顺序由 OrderedDict 保证（组内索引顺序、跨组顺序稳定）。✓
- **缺口**：① `count_by_query`/`agg_terms`/`sample_by_query`/`get_unique_values`（单索引参数）对**逗号分隔多索引**整串路由到单个 provider client（旧引擎单 client 同样无法跨集群，无回归，但 `"a,b"` 会作为整体走 fnmatch/默认，若 a、b 分属两集群会 miss 一个）；② `_ensure_index` 守卫在多索引请求下只覆盖每组第一个索引（P12）；③ `insert_with_vectors` 仅写默认索引（与旧一致）。测试 `test_router_exact_and_pattern_route_and_reuses_provider`、`test_dual_budget_and_cross_provider_index_are_preserved`、`test_same_provider_indexes_each_get_the_route_budget` 覆盖了基础路由，8/8 通过。

## 4. ES8.17 正确性核对（审核重点 4，静态 + 真实）

- **client 参数**：`Elasticsearch(hosts, request_timeout, max_retries, retry_on_timeout, verify_certs, basic_auth/api_key)` 均为 8.x 合法参数；版本门 `8.17.*`（es8_client_router.py:218-223）。venv-es817（8.17.2）实测初始化成功。✓
- **native ANN/KNN**：向量检索确实走 `knn`（field/query_vector/k/num_candidates/filter），nested 字段包 `{"nested": {"query": {"knn": {...}}}}`；真实集群（serverless 与 PaaS 的 8.17.0）均返回 200 且有命中；mapping 已确认 `index_options.type=hnsw`。✓
- **inner_hits 位置**：`a36efc72` 把 inner_hits 放在 nested 层（es8_search_interface.py:448-458）；真实 dual 检索通过（未触发 `[knn] unknown field [inner_hits]`），且 `_restore_inner_embeddings` 与 `_nested.offset` 语义匹配。✓
- **候选数量**：`num_candidates=max(k, max(100, k*10))`；`search_by_vector(size=10000)` 时 candidates=100000，可能超 provider 上限（未验证边界）。⚠
- **分数语义**：native cosine = 1+cosine（实测 1.55 附近），与旧 script_score 量纲不同（P13）；`min_score` 与 kNN 的组合语义未验证。⚠
- **`_id` 排序**：ES8.17 默认禁用 `_id` fielddata → `search_after` 默认参数直接 400（P1）。✗
- **`dims`/`similarity`**：mapping 用 `dims`/`similarity`/`index_options.type=hnsw`（旧 7.10 会静默丢弃这些键——旧代码注释 `_MAPPING_IGNORED_KEYS` 也说明这是升级后需重新审视的点）。✓

## 5. 已执行测试与结果

| 测试 | 环境 | 结果 |
|---|---|---|
| `tests/test_es8_interface.py`（8 个用例，fake client） | miniconda py3.12, pytest 9.1.1 | **8 passed**（仅验证 mock 层，未覆盖 agg_terms/search_after/scroll/真实 client） |
| `tests/test_dual_route_recall.py`、`test_es_mapping_compare.py`、`test_delete_by_file.py`、`test_search_response_ids.py`、`test_insert_check_duplicate_arg.py` | 同上 | **86 passed**（旧引擎逻辑回归，作为行为基准） |
| 仓库全量 `pytest tests/ --continue-on-collection-errors` | 同上 | **599 passed, 2 skipped, 11 collection errors**（11 个 error 均为无关模块缺依赖，如 pdf/data_loader 类，非 ES8 引起） |
| kdb-forge `tests_unit/` + `test_es8_merge_regressions.py`（离线） | venv-es817 | **77 passed, 9 failed**（失败在其 kdb 重建项目自身对齐契约，FakeEngine 注入，与本引擎无直接关系，仅供参考） |
| 工厂链路：示例配置 | venv-es817 | **失败** `ValueError: 重构版要求 Elasticsearch 8.17.x，当前配置为 'es8.17'`（P3） |
| 工厂链路：真实 runtime 配置 | venv-es817 | **成功** `EsSearchInterface → EsSearchInterfaceES8`（providers=serverless,paas） |
| 旧扁平配置在 8.17 client 下 | venv-es817 | 初始化成功（自动检测→Ori），真实 search 被旧 ES7.10 集群 **406** 拒绝（P12） |
| 差分复现 `tmp/es8_audit_diff.py`（A–H 8 组，fake） | venv-es817 | 证实 P1、P2、P4、P5、P6、P7、P8、P9 的全部差异 |
| 真实集群只读探测 `tmp/es8_audit_readonly.py` | venv-es817 | serverless 8.17.0（66 个迁移索引）、PaaS 8.17.0（10 个业务索引）、旧 serverless 7.10.0（342 索引） |
| 真实集群只读验证 `tmp/es8_audit_real_ro.py` | venv-es817 | HNSW mapping ✓；`_ensure_index` 守卫 ✓；search_by_vector(size=5/30) ✓；dual search_multi ✓；search_multi_by_page(size=5/10000) ✓；scroll ✓；agg_terms 结构回归 ✗；search_after 400 ✗；count/get_unique_values ✓ |
| 真实跨 provider 检索 | venv-es817 | 路由解析 ✓；双集群多索引 search_multi（10+10，total=42）✓；PaaS KNN ✓ |

**真实 ES 只读范围内未执行任何写操作**；写路径（insert/update/delete/update_by_query/update_value/put_mapping/refresh）仅在 mock 层验证。

## 6. 尚未验证的场景（待验证项清单）

1. **ES8 写路径真实验证**：insert（含 indexes 零向量过滤、refresh_imm）、update（dotted 字段）、delete、update_by_query/update_value（软删除 del_flag=1 的 delete_by_file 全链路）、`update_index_map`。原因：新集群现有索引均为迁移 staging 索引，属迁移工作流资产；无明确授权可写，按「不擅自创建或借用业务索引」原则未执行。
2. **检索质量对拍**：旧 ES7 源索引 vs 新 ES8 迁移索引的 gold query 召回 overlap/recall@k/排序一致性（BM25、native KNN、dual 合并）。需两侧同时跑同一批 query，属业务验收项。
3. **高负载/并发下的分片取消行为**：本次为单飞只读探测；新集群是否会出现旧集群的 task_cancelled_exception 及新引擎的重试/上抛策略表现（P4/P5 的实际影响面）。
4. **`search_after` 修复后的行为**（当前已坏，无从验证）。
5. **`min_score` 与 kNN 组合、`num_candidates` 上限**（size 极大时的边界）。
6. **`get(index="a,b")` 多索引语义**（旧引擎单请求逗号串在 ES7 上的行为未实测，新引擎改为逐索引查找）。
7. **scroll+vector、`search` size>10 向量召回的业务影响**（当前仓库内无相关调用方）。
8. **kdb-forge 集成测试（真实 ES 写回环）**：`/root/kdb-forge/tests/` 的 roundtrip 类测试涉及建索引/写入，本次未运行（写授权缺失）。

---

## 7. 问题分类汇总

- **新增错误（本实现引入，旧版无此问题）**：P1（search_after 死代码）、P3（示例配置 es_version 不一致）。
- **兼容性回归（旧行为被破坏/变味）**：P2（agg_terms 契约）、P4（异常语义）、P5（拆批保护缺失）、P7（total 口径）、P8（noop/not_found 语义）、P9（scroll 静默丢 vector）、P10（_source 体积）、P11（auto_update_mapping 失效）。
- **ES8 升级带来的必要变化（需文档化/适配，不属缺陷）**：native KNN k/num_candidates 与分数量纲（P6 部分、P13）、旧索引 fail-closed 需 reindex（P12）、双 client 运行时隔离（P12）、`_id` 排序被禁用（P1 部分）、`body=`/http_auth 移除。
- **旧版已有问题（与本次替换无关）**：旧 `search` except 引用未定义变量（es_search_interface.py:762）、`update_del_flag_batch.py` 调用不存在的引擎方法、旧 insert/update 把幂等 noop 当失败（新实现已放宽，见 P8）。

## 8. 最终结论

- 接口与工厂层面：方法齐全、签名/默认参数兼容，上层 `SearchDataInterface` 及服务层无需改代码即可完成「工厂 → ES8 引擎」初始化（真实配置已验证），PaaS/Serverless 路由对上层透明（真实跨集群检索已验证）。
- 检索层面：native KNN/HNSW、BM25 双路、过滤、分页、scroll、聚合、去重、跨集群多索引均已在真实 ES8.17 集群只读验证可用。
- **但「仅改配置即可替换」目前不成立**，阻断项：
  1. `search_after` 完全不可用（P1，死代码 + ES8.17 `_id` 排序 400）；
  2. `agg_terms` 返回契约破坏导致 `list_file_names` 类型分布静默为空（P2）；
  3. 仓库示例配置初始化失败（P3）；
  4. 前提性要求：业务索引需完成 HNSW reindex 迁移（旧索引被守卫拒绝），且新旧引擎须分 venv 部署（7.10 与 8.17 client 互斥，实测 406）。
- 修复 P1–P3 并完成迁移后，剩余差异（P4–P11）为「可接受的升级变化」或「需业务确认项」，建议逐项决策后放行灰度切换；**测试通过 ≠ 功能完整替代**，写路径与检索质量对拍仍需按待验证清单补做。

## 附：本次产生的验证脚本（未提交、未推送，位于已忽略的 tmp/ 目录）

- `tmp/es8_audit_diff.py`：新旧引擎 fake-client 差分复现（8 组）。
- `tmp/es8_audit_readonly.py`：三集群只读版本/索引探测。
- `tmp/es8_audit_real_ro.py`：真实 ES8.17 只读功能验证（mapping/KNN/dual/分页/聚合/search_after/count）。
