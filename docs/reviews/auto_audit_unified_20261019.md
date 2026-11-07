# 自动审核接入统一引擎：实现与验证

> 本文保留上线前验收快照。现已按本次授权在main发布，并按用户纠正保持原all范围；当前状态见 [发布与入口检查](auto_audit_main_deployment_and_entry_audit_20261019.md)。早期“先限定Olive”建议不得作为生产限制。

日期：2026-10-19。状态：**隔离实现已完成，尚未发布、启用生产 cron 或补审业务知识。**

## 修复结果

自动审核已由直接创建 `Elasticsearch` 改为使用检索、挖掘共用的 `EsSearchInterface` 工厂。读取线上业务配置的 `search_engine_config_path` 后，查询、统计和字段更新均走同一引擎与 Router；审核脚本不再编写 Painless、读取 provider 凭据或直接调用 ES API。

旧 `--config <engine.json>` 入口保留，新增互斥 `--search-config <业务配置>`。现有检索 HTTP 接口、业务消费者、嵌入与召回参数、物理索引名保持。新维护模式显式关闭该实例的默认建索引和自动 mapping 更新，不影响普通检索/插入实例。

## 源码现场

- 隔离 checkout：`/root/knowledge_database_builder-auto-audit-20261019`。
- 分支：`codex/auto-audit-unified-20261019`。
- 基线：`9f02bffda2d736d19b3dde0e8266282096afe248`，与 main 生产机器当前发布 HEAD 一致。
- 已 fetch 核实 origin/main；没有切换或覆盖旧服务 checkout 的脏改动，没有 commit/push。
- 最新逐文件 SHA256、业务文件不变证明和测试统计见 [manifest](auto_audit_unified_20261019/manifest.json)。
- 包含新增源码/schema/测试的完整可审补丁见 [code.diff](auto_audit_unified_20261019/code.diff)。

## 实现范围

| 文件 | 改动 |
|---|---|
| `control_script/timing_auto_audit_kg.py` | 保留原审核业务规则，改用统一引擎的索引检查、完整计数、质量分布、字段更新。固定每轮时间阈值；结构化结果区分 dry_run/success/skipped/partial/failed；失败返回非零。 |
| `control_script/timing_auto_audit_all_indexes.sh` | 使用旧项目 ES8 独立解释器与线上业务配置，兼容接收旧 cron 参数但不再 source 激活 ES7；正确合并 stderr，flock 覆盖完整进程并传递退出码。 |
| `knowledge_interface_tools/es_maintenance.py`（新增） | 统一索引盘点、存在性、严格 terms 统计、维护更新选项，以及原生更新的异步 task/批次/错误检查。错误只保留安全类型和确认计数，不保存正文/凭据。 |
| `knowledge_interface_tools/es_search_interface.py` | 工厂新增可选 `maintenance_mode=False`；仅维护实例禁建库、禁自动 mapping，旧 ES7/OpenSearch 适配器复用公共维护能力，正常默认行为保留。OpenSearch 补齐委托既有原生更新实现。 |
| `knowledge_interface_tools/es8_search_interface.py` | 维护选项接入现有 PaaS 原生和 Serverless PIT/CAS 更新；维护 scroll_size 限制页大小，超时与未知写入禁重放。原公开 CRUD/search/count 方法签名保持。 |
| `knowledge_interface_tools/es8_client_router.py` | 新增按 provider 获取已有配置连接池，供统一库存枚举；原按 index 路由解析与连接选择方法未改变。 |
| tests / function_schema / 架构图 | 新增行为回归、只读验证工具、逐函数 schema 及架构说明。原审核异步回归迁到真正共用的维护更新实现，没有删除对应行为覆盖。 |

原条件更新测试包含“引擎整文件 hash 不变”的历史保护；本轮明确修改了两个适配器，因此仅对这两个文件移除此旧快照限制。业务/服务文件 hash 约束、公开方法签名 AST 对比仍保留。该调整不代表放宽接口契约。

## 业务规则与故障边界

原规则保持：document/html、`audit_result=-1`、默认入库满 24 小时；high→2，非 high 且非 segment→0；非 high segment 保留。原来未排除软删除文档，此次继续保留并显式报告其数量。auto_learning 等其他来源未纳入。

每轮以固定时间阈值统计并复核剩余集。并发人工审核会因原 query 或 CAS 版本保护被排除/冲突，不覆盖、不自动重试覆盖。部分失败保留已确认的成功分支及安全计数；未知写入数量标记 `accounting_complete=false`，退出非零。操作不承诺事务或自动回滚。

原生更新仅对已确认零进展的写入大小拒绝减小批次重试；未知传输结果不自动重放。字符串 task ID 轮询至真实完成，完整保留终态 error。失败、缺统计、错误计数、task 超时均不能报成功。Serverless继续复用已发布的完整 stored source + PIT + CAS bulk 实现，没有新增第二套写入策略。

## 实际验证

### 离线回归

最终 **337 passed，384 warnings，6.82s**：新增统一审核文件 31 项，既有审核回归 19 项，其他相关旧检索/CRUD/统计/路由回归 287 项。warning 为既有 Pydantic 配置弃用和 commons 的字符串转义提示。

写路径测试使用真实 `AutoAuditProcessor → EsSearchInterface → ES8/ES7/OpenSearch` 实现，只替换最末端 ES I/O。覆盖精确阈值及前后边界、high/其他/缺失质量、QA/segment、auto_learning 排除、人审状态、软删除、完整正文/四类向量与对象保真、61 条跨批、最新 PIT 关闭、并发人工审核 CAS 冲突、重跑、未知写入不重放、任务完成/超时、失败退出、索引不存在不创建、跨 provider 清单与失败。shell 在隔离临时目录验证空格路径、退出码 3、stderr 合并、flock 冲突退出 75。

这些是离线 API 参数/内存状态验证，**不是对真实 ES 的写入验收**。

测试命令（复用现有离线 8.17 环境，不修改任何服务解释器）：

```bash
cd /root/knowledge_database_builder-auto-audit-20261019
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /root/kdb-forge/.venv-es817/bin/python -m pytest -q \
  tests/test_auto_audit_unified_20261019.py \
  tests/test_auto_audit_update_by_query.py tests/test_auto_audit_time_threshold.py \
  tests/test_es8_interface.py tests/test_es8_conditional_integration_20261008.py \
  tests/test_es8_autocreate_20261005.py tests/test_es8_native_batch_20261009.py \
  tests/test_es8_source_compat_20261009.py tests/test_dual_route_recall.py \
  tests/test_search_response_ids.py tests/test_es_mapping_compare.py \
  tests/test_delete_by_file.py tests/test_insert_check_duplicate_arg.py \
  tests/test_from_type_count_api_20261008.py -p no:cacheprovider
```

证据：[pytest.xml](auto_audit_unified_20261019/pytest.xml)、[pytest.txt](auto_audit_unified_20261019/pytest.txt)。

最初把 `test_off_task_es817_20261008.py` 也加入扩展命令时，现有离线环境缺少 `fire`，出现 collection error，整轮未执行。这不是此次新增断言失败；未安装依赖或修改全局/服务 venv，后续排除此文件单独运行上面 337 项。该挖掘模块的完整测试本轮未验证，保留 [collection 日志](auto_audit_unified_20261019/pytest_collection.txt)，不称全仓测试通过。

### main 真实只读

工具：`tests/auto_audit_readonly_20261019.py`。通过 SSH 将五个候选模块加载到 main **独立 Python 进程的内存**，使用旧项目现有 `.venv-es817/bin/python`（Python3.9/ES client8.17.2）与实际线上业务配置。未写入远端源码或配置，未调用运行服务。请求守卫只允许 HEAD、版本/cat GET、count/search POST，持久写请求在发出前被拒。

最终候选 dry-run 及独立原生 count 一致：

| 目标 | 实际 provider | 满 24h 待审 | high→2 | 其他可处理→0 |
|---|---|---:|---:|---:|
| payoneer_olive | PaaS | 952 | 814 | 138 |
| mercado_local | Serverless | 0 | 0 | 0 |

真实枚举两个 provider 后得到 109 个路由归属正确、去重、排除系统索引的物理索引。返回完整清单供范围复核，**不能据此认为109个全部获准补审**，其中迁移临时/测试索引仍需核对。

为核验最终源码分别进行了四次低负载只读候选运行，每次 16 个 HTTP 读取，共 64 个。最新完整证据（含截止时间、元数据统计、所有目标清单、每次请求路径及候选模块 SHA）见 [main_readonly.json](auto_audit_unified_20261019/main_readonly.json)。无模型/embedding 调用，无 PIT/scroll 创建，持久写 0。

初次诊断为 965 条，此次为 952 条。此次未执行审核写入，减少的 13 条不能归因于本次修复；其他写入者/人工操作的来源未核查。

### 生产保持

再次只读确认 main HEAD 仍是原发布版本，审核 Python/shell SHA 与排查开始时一致，原每小时旧 cron 仍在。检索 PID 47173、挖掘 PID 1533339 与开始观察一致。服务/配置/cron/审核状态没有被本次实施修改，证据 [production_unchanged.json](auto_audit_unified_20261019/production_unchanged.json)。

## 待发布与后续验收

1. **尚未 commit/push、部署或启用。** 用户本轮“好”承接实现方案，不延续历史生产发布授权。后续发布必须使用当次明确指令，目标目录 git pull；不能直接覆盖生产代码。
2. **尚未真实写测试。** 如需执行，先明确当次允许的隔离索引，验证 PaaS/Serverless 当前实现的成功/失败和全字段保真。历史 `test_case` 授权不在此次自动扩大使用。
3. **初次启用范围建议限定 Olive。** 全量109项清单先核对临时索引；候选 wrapper 的原 `all` 语义保留，但不可未经范围复核直接启用全量写任务。可使用 `AUTO_AUDIT_INDEX=payoneer_olive` 指定首次范围，读取同一线上业务配置，无须修改连接地址。
4. **补审前重新 dry-run。** 952 只是此次观察值，不能作为固定写入清单。重启检索、挖掘服务不是这次启用的必要步骤。
5. **回退边界。** 生产启用时先备份 cron/入口配置及写入清单；异常先停用新审核入口，不能自动切回继续审核旧库，也不能无条件撤销审核状态。

仅供下一次明确授权后使用的定向 dry-run：

```bash
cd /root/knowledge_database_builder
.venv-es817/bin/python control_script/timing_auto_audit_kg.py \
  --search-config config/config_for_search_index.json \
  --index payoneer_olive --from-type-norm document,html --hours 24 --dry-run
```

当前未发布版本在 main 不能直接使用此命令，实际候选验证应使用上述只读工具；不要为了运行候选而覆盖生产源码。
