# 旧8003联合检索缺索引阻断：只读定位

2026-10-05；承接 wholeagent 的旧项目端到端测试反馈。本轮仅定位、限量真实只读对照与保存证据，没有修改实现、运行配置、索引或任何业务数据，没有再次重启、commit/push。

## 结论

确定的 P1 兼容回归在**当前运行的 ES8 引擎**：联合检索中一个索引不存在会抛出 `elasticsearch.NotFoundError(404, index_not_found_exception)`，并中断其余索引结果的返回。旧 ES7 在线 `search_multi` 的 msearch 合并会跳过失败子请求，继续返回成功的公库命中。

这不是私库被路由到错误集群，也没有证据表明此故障由 ext_info 补丁或本轮数据迁移丢失造成。SG 上两个测试私库实际不存在：`mercado_sg_retrieval_test` 在 Serverless、`payoneer_sg_retrieval_test` 在 PaaS，均 HEAD false；对应公库均存在。测试私库不是补建或数据写入的授权范围；不能通过创建空索引或改上游请求掩盖引擎的容错回归。

同一配置下加载现有隔离开发源码 `07d08…` 做真实只读 BM25 对照，已经恢复这一行为：两种联合顺序都保留公库命中；仅缺失索引返回 `([], 0)`。**运行中的 8003 仍使用 caedc4…，因此这项隔离修复尚未生效。**17:35 的本机重启只加载已验收的 service ext_info 两函数补丁，未夹带隔离引擎审计修复。

## 源码与实际异常

运行 checkout `/root/knowledge_database_builder`，分支 main、HEAD `a36efc7245dedf2492f5be396f87390885f3a4f4`；unit `knowledge-database-search.service`，MainPID `3178826`，8003。

- 运行引擎 SHA256：`caedc4d3269af3a24a8f2f5104e37c60704f8920b11158dc98236f8942abc145`。
- 隔离引擎 SHA256：`07d08eb5daa3daccb87b5297f43c30f9b507713cf978567fa5b8f555a9b1291e`；路径 `/root/knowledge_database_builder-es8-dev/knowledge_interface_tools/es8_search_interface.py`。
- 运行 service SHA256：`c4f81d69c59159b57072bf10253e2055232cb74224ea4d905c843799511a72db`。
- 未改业务层 SHA256：`224e12340f627a5b9e5bde0ac6c934f78f072eb7ffc804dc290ce18d944c385e`。

实际运行日志 `/tmp/kdb-search-8003.log` 中的异常链为：

1. `knowledge_database_search_es.py:349` 的 `/search` → `query_remote_service:287`。
2. `search_index_data_interface.py:1151` 调用 `engine.search_multi`。
3. 运行 `es8_search_interface.py:888` → `_search_multi_group:853` → `_search_request:549` → ES client search。
4. ES 返回 `NotFoundError(404, 'index_not_found_exception', 'no such index [mercado_sg_retrieval_test]')`；payoneer 同类错误由真实只读对照确认。
5. 运行引擎没有子路隔离，异常上抛到服务。`knowledge_database_search_es.py:428–435` 的既有错误分支重试三次后返回 HTTP200 的一条 `q=检索结果错误, id=null, score=0` 哨兵。

因此公库先查也不能解决：其结果积累在 helper 内，后续私库异常导致 helper 未能正常 return。约3.4–4.1秒和该服务的三次尝试、两次1秒等待一致；计时由 wholeagent 实测，本轮没有再次执行带 embedding 的 HTTP 请求。

旧实现 `es_search_interface.py:1390–1406` 检查每个 msearch response 的 `error` 后 `continue`，保留其他命中。隔离新实现 `es8_search_interface.py:1461–1466` 已按每索引/召回路 catch、记错并继续。该措施位于在线召回入口，不应扩大成维护操作或 mapping 守卫一律吞异常。

## 实际只读最小矩阵

证据：[脱敏结果 JSON](es817_missing_private_index_readonly_20261005.json)。使用现有 ES8.17 venv、真实 Router/真实引擎/同一运行配置，禁用 ensure/auto mapping 已核实为原配置 false。两条 workflow 原查询各 BM25-only、QA过滤、size=1；没有 embedding/LLM调用，没有原文、向量数值、凭据落盘。

每个 provider 均取得以下结果；共16次公开引擎调用加4个 HEAD 存在性检查。

| 请求形状 | 运行 caedc4… | 隔离 07d08… |
|---|---|---|
| 公库 | 1条有效ID | 1条有效ID |
| 缺失私库,公库 | 抛404 | 公库1条有效ID |
| 公库,缺失私库 | 抛404 | 公库1条有效ID |
| 仅缺失私库 | 抛404 | 空列表，total=0 |

mercado 公库上述成功调用 total=173；payoneer=80。这是该 BM25 查询的引擎命中口径，不是完整业务规模或 ANN 质量。

wholeagent 的实际 HTTP QA/segment 联合请求、五客户 workflow 回放证据在 `/root/sell_agents/tmp/sg_retrieval_20261004/workflow_sg_trace_8003_20261005.json`；其补充对照报告旧120.77纯公库/两种联合顺序均3条、仅不存在索引0条，SG对应联合和缺失单库均错误哨兵。本轮没有直接用 ES8 client 请求旧ES7，也没有独立重跑旧端 HTTP矩阵。**BM25 引擎层对照不能冒充当前服务已经通过 dual/业务重排/完整 workflow验收。**

## 修复与激活边界

- 已有隔离代码能处理本例；不需要改变工作流 index_names、改私库物理名、内部别名映射或新建空私库。
- 如果采用最小补丁，仅在运行旧项目的在线 `search_multi` 每索引/每路请求异常边界恢复旧容错；保持 native KNN、原请求/响应、日志可观测性及维护接口严格行为。不能仅外层 catch 后返回全空，否则仍丢掉成功公库结果。
- 如果加载整个隔离引擎，还会带入其他审计修复/仍待确认限制，不能把这一个反例通过当作整版发布批准。
- 本反馈明确请求“只读定位”，本轮未应用任何引擎补丁，也未再次重启。后续本机激活应单列具体改动和回归证据，不能重新要求无关远端 commit/push；真实生产更新仍遵守目标工作目录 git pull。当前无 commit/push 授权。
- 本例验收必须包括双方 provider、私库前后顺序、仅缺库、QA/segment、dual召回及真实消费者回填和排序，最后由 wholeagent 原 workflow 再测。实际写验收仍仅限此前明确合成范围，不可扩大到业务/staging。

此前“重启后真实 HTTP CRUD 28项全过”只覆盖准确自有合成索引生命周期和单库读写，不覆盖缺失私库联合查询；本阻断使端到端整体验收仍未通过。Wayfair segment 8/10重合是另一项检索质量差异，本例404修复不能解释或关闭它。

## 用户指出自动建库后的补充

旧版常规路径在 msearch 前会逐索引 `_ensure_index` 并创建缺失库；前文仅解释 msearch 跳过失败子请求不完整。当前 ES8 ensure 开关 false 与首索引漏检使这一旧行为未保持。旧端用 /search 查不存在名称可能实际创建索引，不能只凭返回正常即称只读。详见 [自动建库契约核对](es817_auto_create_contract_readonly_20261005.md)。本轮仅源码/既有配置核对，真实建库未执行。
