# 旧项目 86 原名索引增量同步执行验收

任务：`ES817-INCREMENTAL-SYNC-20261009-OLD`。隔离开发目录 `/root/knowledge_database_builder-es8-dev`，分支 `codex/es817-old-engine`，源码 HEAD `a36efc7245dedf2492f5be396f87390885f3a4f4` 加原有未提交工作。本 agent 只新增维护包装、测试、schema 和记录；引擎、Router、工厂、业务、服务及复用维护组件与接管时 SHA 相同。未提交、推送、部署、重启或修改任何运行配置。

**本次补差完成：真实写入并独立完整 `_source` 读回验证 230 个文档，其中新增 213、更新 17。最终 86/86 索引两端各 202,962 根文档，ID/routing 集合、`del_flag`、`audit_result`、`quality_level` 的索引值差异均为 0。** 最后身份复核于北京时间 2026-10-09 01:28:23 完成；复核本身没有新增文档写入。没有全量重读未推进时间的任意其它业务字段，因此不宣称当前全部正文字段或持续同步已经验收。

## 实际写入与检查结果

| 原物理 index | Provider | CREATE | 完整字段 UPDATE | ACK 后完整原生读回 |
|---|---|---:|---:|---:|
| wayfair_test | Serverless | 5 | 0 | 5 |
| joint_login | Serverless | 87 | 2 | 89 |
| mercado_local | Serverless | 6 | 0 | 6 |
| payoneer | PaaS | 5 | 13 | 18 |
| mercado | Serverless | 53 | 2 | 55 |
| wayfair | Serverless | 26 | 0 | 26 |
| payoneer_olive | PaaS | 31 | 0 | 31 |
| 其余 79 个既定索引 | 原 Provider | 0 | 0 | 0 |
| 合计 | 81 Serverless / 5 PaaS | **213** | **17** | **230** |

17 次更新包含三条已报告的删除标记修正：Mercado 两条 `0→1`，joint_login 一条 `1→0`。复制旧端已有当前状态，没有重新审核。其余 14 条更新为 Payoneer 13 条 `insert_time/update_time` 对齐和 joint_login 一条既有业务字段/时间对齐。三条标记记录同时复制其余发生变化的源字段，不能只对齐标记而留下不同的业务内容。

| 检查 | 实际结果 | 证据/范围 |
|---|---|---|
| 固定时间窗口候选 | 86/86、340 条完整 source 读取与读回通过 | 历史 checkpoint 下界 `gte` 重叠，固定原生业务值上界 `lte 2026-10-09 00:30:00`；不假定时间字段是 CDC |
| 最后一次窗口写入 | 326 条完整 source 已相等；14 条更新 | 前批已写入的记录计作 noop，不重复计写入/知识数 |
| 实际受影响的不同文档 | 230 | `(index, _id, routing)` 去重；逐条 ACK 与完整源 SHA 读回相等 |
| 所有完整 source 验证的不同文档 | 340 | 包含新增、修改和未改动窗口边界记录；不累加重复批次验证次数 |
| 最终身份及三个标记字段 | 86/86、双方 202,962；缺失 0 / 额外 0 / 标记差异 0 | 原生 ES7 scroll、ES8 PIT；`_source=False` + 三字段 docvalues；完整唯一集合比较 |
| 最终 size=0 统计 | 86/86、请求失败 0、逐索引统计差异 0 | del_flag 各状态、审核状态和根 title/content 向量存在性匹配；不是所有内容验收 |
| 目标 `_source` 存储裁剪 | 0 个索引 | 当前固定 86 项 mapping；未通过列值回填冒充完整 stored source |
| 陌生目标跳过 / CAS 冲突 / 未知写入结果 | 0 / 0 / 0 | 实际 journal 和结果；失败保护依然保留 |
| 本轮最终流程失败索引 | 0 | 两个先前 metadata 失败阶段单列在下文，未抹掉或冒充成功 |

213 条新建记录都保留源端的 `del_flag=0`；原 title、content、indexes 三条向量路径各保留 213 个非空向量实例，均通过 1024 维、有限数值与非零校验。对应源数据没有 image embedding，未创建或猜测图片向量。17 条既存更新的四类向量路径和 nested 内容都与更新前相同，正文/向量没有重新生成。完整 `_source` 比对同时涵盖时间、ext_info、标签、task_id、业务字段、缺失字段形状及所有既存向量。

## 安全复用和写入边界

固定范围由 `docs/reviews/es817_physical_names_20261004/prepared_plan.json` 中的 86 个 **original 物理名**决定，canonical SHA 为 `5b8c8528a4913d6df28d4e89cb427f4b1a00a0cae959402931564e0b7f79c77f`。没有改用后缀 staging，没有增加历史排除 17 项、replay、test_case 或默认 open_shop。父会话负责 120 上线，与此维护执行分开。

已验证的目标旧内容基线为：Serverless 81 份最后完整 source 指纹 124,642 根；PaaS 五库原名完整迁移备份 78,107 根，gzip SHA、完整指纹/条数复验通过，并叠加 Olive 已授权单条修正的 ACK 指纹。总基线 202,749 根。PaaS 本地备份检查没有重新扫描远端数 GB 源正文。

正常写入流程为：缺失/标记集合和固定窗口提供候选 → 有界原生完整 source mget → 与已证明的历史目标指纹三方分类 → 私有完整 before/after 与指纹落盘 → `create` 或 fresh GET + `if_seq_no/if_primary_term` 完整 document `index` → 逐条 ACK → 独立原生 HTTP `_source=True` 读回比较 → 成功后才更新自有基线。复用 `tests/rebuild_es8_source_local_replay.py` 的 `fingerprint`、`source_rows`、`write_rows` 等组件，**没有运行其中重建、锁库、恢复或 replay 主入口**。

写前完整备份在 `data/es817_incremental_sync_20261009_*`，目录 0700、JSON 0600。它们含正文/向量，保持私有，不纳入公开报告或提交。收尾本地属性检查核对 1,091 个私有路径：完整 before/after 文件始终 0600；137 份仅计数/状态的 metadata journal 原继承 0644，但其父目录始终 0700，现已收紧至 0600，最终属性不符 0。此检查没有 ES 写入，见 `artifact_checks.json`。目标一旦不是可信旧内容、发生并发更新、或者响应不完整，保留而不强盖；不是把当前新端值重新登记成自有旧基线。源 ES7 始终只读，旧写者继续可写；没有硬删源/目标、审核知识、改 mapping/alias/锁/路由、建删索引、修改运行服务或生成 embedding。

## 前期失败保留及最终复验

1. 本地 lineage 包装首次把历史 `completed=86` 整数当布尔值检查，执行前拒绝。保留 `data/es817_incremental_sync_20261009_lineage/failure.json`；按真实历史结果契约检查 `completed=planned=86` 后重试成功。未向 ES 发写请求。
2. 第一轮优先身份同步完成五库 179 条 ACK，但 Mercado_local、Olive metadata 枚举未通过，两个索引尚未形成候选 intent/bulk，写入 0。保留 `data/es817_incremental_sync_20261009_identity_priority/results.json`。独立 Mercado_local 原旧读取诊断观察到第三页 2 个 `task_cancelled_exception` 失败分片，返回部分命中，已按完整性守卫拒绝；没有把部分页当完整或在同 cursor 上继续。
3. 后续 metadata 读取改为 `_source=False` + docvalues，避免只取标记却解析大型存储正文。最初对任意 `terminated_early=true` 拒绝的守卫过于严格，三次新整库上下文尝试仍拒绝 Mercado_local，中间页当时所有分片成功。保留 `data/es817_incremental_sync_20261009_mercado_local_retry`，没有写入。随后先通过独立完整时间候选安全补齐 Mercado_local 6 条和 Olive 31 条，共 37 条 ACK，避免这个 metadata 诊断挡住已证完整的源记录。
4. 最终 metadata 仅接受已经取到末尾空页、全部成功分片、唯一身份数等于精确 total、前后独立 native count 相同的枚举。遇到中间 early 标志，再做同查询独立 identity-only 全集合对照和每库最多 10 条原始标记 mget。实际 **11 个旧索引**通过此附加证明，**110 个有限原始标记样本**匹配；不能据此猜它一定是某种 ES 优化，也不能放宽完整正文捕获守卫。最终 86 项首次 metadata 尝试都成功，失败重试数 0，所有 scroll/PIT 最终关闭。

公开证据保留成功与失败阶段的分项，不把 `completed=true` 自动解释成每项成功。第一优先阶段的两项失败和随后三次保护性拒绝都是历史失败；最后全范围复验的 `failed_indexes=0` 才是本轮收尾状态。

## 测试、变更与可复核材料

本次新增两个维护包装与一个回归文件：

- `tests/es817_incremental_prepare_20261009.py`：只读基线准备、固定范围/窗口与候选分类，无隐式写入口。
- `tests/es817_incremental_apply_20261009.py`：显式 `--execute` + 冻结 scope SHA，完整源捕获、历史指纹保护、CAS/ACK/读回及三字段身份验证。
- `tests/test_es817_incremental_20261009.py`：18 个参数化行为用例，覆盖完整 payload、未知目标、冲突/未知响应拒绝、mget 形状、部分页、PIT 更新关闭、时间重叠/上界/限额以及 early 标志的独立证明。真实写到现有授权 86 业务库的验收在上述 journal 中，不把 mock 参数当真实成功。

新增/修改函数的 27 份实际对应 schema 均在 `function_schema/`；业务架构不变，Architecture 文档只追加维护数据流。所有实际哈希及源码对比见 `manifest.json` 和 `maintenance_tools.diff`。接管时已有其它未提交变更全部保留，本轮未回滚或混入提交。

最终联合命令（只离线边界 mock，没有 ES 测试写）：

```bash
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/root/knowledge_database_builder-es8-dev:/root/knowledge_database_builder-es8-dev/tests \
  /root/kdb-forge/.venv-es817/bin/python -m pytest -q \
  tests/test_es817_incremental_20261009.py \
  tests/test_rebuild_es8_source_local_replay.py \
  tests/test_es8_identity_diff_readonly.py \
  tests/test_es8_deleted_identity_readonly.py \
  -p no:cacheprovider --tb=short \
  --junitxml=docs/reviews/es817_incremental_sync_execution_20261009/pytest.xml
```

结果 **70 passed，1 warning，1.18s**：新增包装 18 项 + 既有复用组件 52 项；warning 为已有 `source.invalid` mock 客户端 TLS 提示。此前 52/13/15/18 次阶段验证不重复累加。此轮不宣称检索引擎或全部接口重新验收。

公开材料目录 `docs/reviews/es817_incremental_sync_execution_20261009/`：

- [metadata_final.json](es817_incremental_sync_execution_20261009/metadata_final.json)：86 项原生身份/三标记对比、页数、独立 count、early 证明与读上下文关闭统计；无原身份、正文、向量、凭据或上下文令牌。
- [inventory_final.json](es817_incremental_sync_execution_20261009/inventory_final.json)：独立 size=0 统计和完整存储 source mapping。
- [final_indexes.csv](es817_incremental_sync_execution_20261009/final_indexes.csv)：全部 86 项 count/diff、写入及证明取样结果。
- [execution_stages.json](es817_incremental_sync_execution_20261009/execution_stages.json)：逐批 CREATE/UPDATE/noop/历史失败、更新字段分类与 SHA。
- [payload_shape_summary.json](es817_incremental_sync_execution_20261009/payload_shape_summary.json)：不同文档去重与向量路径保留数量。
- `pytest.xml`、`artifact_checks.json`、`manifest.json`、`maintenance_tools.diff`：实际离线测试、私有路径权限检查、哈希、维护包装源码差分。

## 仍然不能据此声称的范围

身份和三个 **索引标记值**已全范围比较，时间窗口内 340 个记录已做全部原始字段对齐。其它没有推进 `update_time` 的正文、标签、扩展 metadata、类别等字段，本轮没有重新做 86 库全正文扫描；历史基线 SHA 本身不能证明今天这些源字段未变。这是尚未全字段审计的范围，不是本轮已知 213 个新增或三条标记仍待处理。

docvalues 比较按当前 mapping 的索引语义；缺失与 null 都可能没有索引值，quality_level lowercase normalizer 可能使原始大小写差异不可见。不能把标记索引值相等扩大成原始 JSON 形状全等；实际补差候选复制时则完整保留原始 `_source`。

两端没有全局事务、所有源写者没有冻结，也没有经验证的持续 CDC。窗口上界之后或各索引快照之后仍可能发生新变化。当前结果是本次固定窗口及独立逐库快照的验收，不是承诺未来永远一致；未镜像硬删除，也没有把合法新端写入当成旧数据覆盖。存储 GB 差异的不同范围/历史槽位结论见父会话 [预检报告](es817_incremental_preflight_20261009.md)，不能为凑容量扩大到历史排除项。
