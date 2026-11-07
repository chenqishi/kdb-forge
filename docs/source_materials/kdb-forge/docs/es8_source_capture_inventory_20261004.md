# 增量来源写入入口盘点（2026-10-04）

核查时间：2026-10-04 03:44 UTC／北京时间 11:44。仅读取本机代码、systemd、进程环境中的配置路径；未请求旧／新 ES，未修改或重启服务。**结论：现有本机证据不能证明所有真实旧 ES 写者已覆盖，持续同步尚未开启。** 目标消费器可用，不等于已有可靠来源日志或完整历史基线。

## 运行接线与边界

| 服务 | 只读事实 | 对捕获的影响 |
| --- | --- | --- |
| `kdb-forge.service`，8010 | active；PID 1305527；2026-10-01 11:42:37 CST 启动；工作目录 `/root/kdb-forge`；入口 `kdb.api.app:app`；实际 Python 3.9；进程环境 `KDB_FORGE_CONFIG=config/config_test.json` | 配置再指向 `/root/knowledge_database_builder/config/config_es_engine.json`；该文件的端点与两个 ES8 provider 均不同，与既有旧来源配置路径一致。这里只确认配置关系，未向端点验证实时写入。 |
| `kdb-forge-retrieval.service`，8012 | active；入口 `kdb.api.retrieval_app:app`；配置 `config_search_runtime.local.json` → ES8 runtime | `retrieval_app.py` 只装载检索路由，不是旧 ES 变更捕获入口。 |
| `knowledge-database-search.service` | active；PID 1381069；入口为旧项目 `knowledge_database_search_es.py`，传入 `config_for_search_index_es817.local.json` → 当前 ES8 runtime | 当前磁盘代码仍声明 `/insert`、`/delete`、`/delete_by_file`、`/update_by_condition` 等写路由。它也是**目标侧潜在写者**，不能仅凭 8012 只读就认定 ES8 没有其他写者；本轮未确认这些路由有无外部流量或外围拦截。 |

8010 进程早于 `src/kdb/es/engine.py` 最近修改时间（10-04 03:21:51 UTC），因此当前磁盘方法不能直接证明该进程已加载相同版本。也未证明其他主机、临时脚本、第三方直接凭据调用或其他用户定时任务不存在。本机进程快照没有运行补字段／自动审核脚本，root crontab 当前零任务；这些都不是“所有写来源已覆盖”的证据。

## 已定位写入面

盘点两个项目 Python 文件，按 AST 列出调用，不执行模块导入或连接 ES。

| 位置 | 已确认操作／缺口 |
| --- | --- |
| `src/kdb/crud/repository.py:60–136`，`src/kdb/crud/legacy_compat.py:353–400,753` | insert/upsert、普通 update、按条件更新、硬删除、按文件软删。只包装 Repository 会漏掉兼容层直接调用 `self.engine` 的路径。 |
| `src/kdb/es/engine.py:652–734,931–1053` | 最接近本项目统一出口：`update(doc_as_upsert)`、`update`、`delete`、`index`、保根向量的 CAS bulk，以及 `update_by_query`。当前磁盘已有 `_source` 根向量补读；其内部批量更新另有 scroll 路径，不可直接当成本次禁止旧 ES scroll 的增量采集器。 |
| 旧 `knowledge_interface_tools/es_search_interface.py:445,479,568,873,959,980` | ES7 原实现直接调用 `update_by_query`、`index`、`update`、`delete`；另一 OpenSearch 实现也有 update/delete。修改 kdb-forge 单一类不会覆盖这些旧入口。 |
| 旧 `knowledge_interface_tools/es8_search_interface.py:652–734,980–1025` | 独立 ES8 写实现；不经过 kdb-forge 的 engine，可成为目标写入协调的旁路。 |
| 旧 `knowledge_interface_tools/supply_missing_field.py:355,449,708` | 自行持有 `self.es`，直接 `update_by_query`／bulk；补字段脚本能绕过两边 Repository／业务服务。 |
| 旧 `control_script/timing_auto_audit_kg.py:307,459,505` | 自行持有 ES client；按条件直接修改 `audit_result`，脚本没有同时推进 `update_time`。 |
| 旧 `search_index_data_interface.py:648–661,802,815,1078` | 插入预处理设置无时区时间；普通 update 直接转发；硬删除无持久 tombstone；文件软删只设 `del_flag=1`。删前快照明确排除向量，不能充当完整 after-image 或可靠 CDC。 |

新 `KnowledgeService.update` 会设置 `update_time`（`service.py:243`），但 engine／兼容直接更新、批量脚本仍能绕过。上述范围未发现 `delete_by_query` 调用或已部署的 outbox／committed producer；不能因此假定范围外没有。时间游标仍会漏普通修改、批量软删、自动审核与物理删除。

## 最小可评审接入方案（尚未实施）

1. **先确定所有写者及独占范围。** 将批准的 86 原名和 provider 显式绑定到统一写协调器；8010、旧引擎和上述维护脚本分别接入，或在协调范围内禁止旁路写。跨机器调用也须纳入。仅在 HTTP route 上补一个日志回调不足以覆盖。
2. **写前持久化 intent，而非成功后补日志。** 在向量与 ID 已确定、真正调用 ES 的位置加入 `SourceWriteCoordinator`。同一 ID 串行；SQLite WAL／持久事务队列记录 operation ID、来源版本、完整 after-image 或删除意图，先事务提交/fsync，再以 CAS 执行来源写入。只有确认成功才提交事件；异常和超时保留 pending，恢复程序核实结果。不能丢掉“ES 已写成功、进程在写日志前崩溃”的窗口，也不能把来源失败的意图交给目标消费。
3. **普通 update 和 upsert 必须重建完整 after-image。** 请求里的局部 `doc` 不能直接当 after-image；在同一来源版本下补齐未改字段及四类向量，并由 CAS／串行协调防止拼接并发版本。写业务操作可以做受控按 ID 补读，检索请求不触发同步；缺数据或向量时停止提交，不重新生成 embedding 冒充旧值。
4. **批量 query 操作不能只记查询条件或 updated 数量。** 对确定的命中 ID／版本记录逐条 intent，转为可 ACK、可恢复的有界操作并记录每条结果；软删输出完整 upsert，物理删输出 tombstone。现有原生 `update_by_query`／可能的 `delete_by_query` 若保留，必须另有能证明每个实际变更的源端日志，否则仍是覆盖缺口。本方案不启动任何旧 ES scroll；需要广泛枚举／历史对账时仍遵守夜间明确命令约束。
5. **封闭日志与历史补差分开交付。** 只将来源已确认的连续处理区间封为 gzip NDJSON＋SHA＋committed manifest，接入[消费合同](es8_change_log_contract.json)。pending 未解决时不能越过封窗。源 cursor／导出 cursor／目标 applied cursor 分离。先开启真实写捕获并固定基线边界，再按获准时间做受控历史对账补差；原全量 dump＋四索引一次增量不能证明此前未记录变更已补齐。

必须单独评审崩溃恢复、并发写者覆盖与来源 ACK 不确定性；增加本地文件格式或声明 `coverage=true` 都不能解决这些问题。直到 writer 清单、历史补差和明确来源截止游标均有证据，`freshness_proven=false`。
