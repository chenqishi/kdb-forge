# 自动审核接入统一数据接口方案

日期：2026-10-19。状态：方案，未修改实现、线上配置或审核状态。

## 结论与现状

现有自动审核没有接统一接口。`control_script/timing_auto_audit_kg.py` 的 `AutoAuditProcessor` 自行构造 `Elasticsearch`，直接使用 `.count/.search/.cat.indices/.update_by_query/.tasks.get`。它既没有调用业务数据接口 `SearchDataInterface`，也没有调用底层统一引擎工厂 `EsSearchInterface`，所以检索/挖掘的 ES8 配置切换不会影响它。

这里的“统一接口”推荐使用项目内的 Python 数据访问接口，继续由独立 cron 进程执行。无需新增 HTTP 接口，也不需要为了定时审核启动 embedding、LLM、类目加载或检索排序依赖。

已核对 main 实际版本 `9f02bffda2d736d19b3dde0e8266282096afe248`：

- `knowledge_interface_tools/es_search_interface.py` 的 `EsSearchInterface` 是既有引擎工厂，按配置选择 ES7、OpenSearch 或 ES8。
- `SearchDataInterface` 已经通过该工厂访问数据；按文件软删除调用 `engine.update_by_query(index, query, update_fields)`。
- main 的 ES8 `update_by_query` 在第 1348 行附近，经 `_conditional_update_responses` 分流：PaaS 使用原生更新，Serverless 使用已有无脚本、完整 source 与版本保护的更新路径。
- 当前本机服务 checkout 的部分引擎源码落后于 main 发布版本，实施应从核实后的发布基线建立隔离 checkout，不拿本机旧实现覆盖 main。

## 建议结构

```text
线上业务配置 config_for_search_index.json
             │ search_engine_config_path
             ▼
      同一份活动引擎配置
             │
检索/挖掘业务 ─┬─→ EsSearchInterface（既有工厂）
自动审核规则 ──┘              │
                 ES7 / OpenSearch / ES8
                                      │
                              IndexClientRouter
                               ├─ PaaS
                               └─ Serverless
```

自动审核脚本是独立的业务调用方，只负责资格查询、high/其他质量分支、24 小时阈值、dry-run 与汇总。它不再持有裸 ES client，不读取 providers 内的连接信息，也不编写 ES 更新脚本。底层接口负责连接、版本、路由、分页/批次、任务等待及写入错误识别。

## 最小改动

| 改动位置 | 调整内容 |
|---|---|
| `AutoAuditProcessor` | 将直接 client 调用改为统一引擎方法；更新只传 query 和 `{"audit_result": 2}` / `{"audit_result": 0}`。 |
| 既有引擎工厂及适配层 | 复用 `count_by_query`、`update_by_query`；补齐统一的索引枚举/存在性检查能力，脚本不越过接口访问私有 client。 |
| 审核统计 | 使用完整性计数，按来源/质量等原规则生成统计；查询失败不得当作 0 条待审。 |
| 统一更新层 | 核验并复用异步 task 等待、批次大小控制、部分失败/冲突统计；审核脚本已有保护缺失时在此层补齐，不复制第二套 ES8 实现。 |
| 定时启动脚本 | 从线上业务配置解析活动引擎配置；使用旧项目 `.venv-es817/bin/python`；修正 `2>1` 为正确 stderr 合并，增加进程锁防重叠执行。 |
| 文档/测试 | 对应 function_schema、架构图和回归测试同步更新，记录生产启用与回退步骤。 |

不更改既有检索 HTTP 输入输出，不新增第二套 provider 路由规则。旧 `--config <engine.json>` 手工调用方式保留；可新增明确的 `--search-config <业务配置>`，二者互斥，供线上 cron 跟随同一个 `search_engine_config_path`。业务配置仅解析指针，不初始化完整 SearchDataInterface 的 embedding/LLM 等无关对象。

审核引擎采用仅访问已有索引的维护模式：不自动创建默认索引或缺失目标，不修改 mapping；此限制只作用于该调用方，不改变正常检索/插入的自动建库行为。配置和 Python client 不兼容时明确失败，禁止静默退回旧库。

## 原业务规则保持

- cron 每小时执行；默认等待知识入库满 24 小时。原 `--hours/--minutes` 参数语义保留。
- 来源只包含原配置的 `document/html`，且 `audit_result=-1`。
- high 写为 `audit_result=2`；非 high 且非 segment 写为 `0`；非 high segment 保持原样。
- 只更新审核字段，不改正文、向量、ID、`del_flag`、`update_time` 等其他业务字段。
- 原脚本没有 `del_flag=0` 限制，本轮不能悄悄添加。之前 965 条范围包含 21 条软删除文档，方案实施时仍应明确展示这部分计数。
- auto_learning、中文“自动学习”等不在本定时任务范围；不能将全部 12,175 条待审作为补审目标。

上述计数来自 10 月 19 日 11:21 的诊断快照，执行前应重新统计，不把 965 当成固定写入数量。

## 全索引与执行结果

`--index all` 由引擎层枚举配置内 provider 的索引，并按同一 Router 的归属过滤、合并去重。索引位于非路由目标的副本不能成为写入对象；路由目标不存在时必须明确报告，不退回另一个集群。

迁移临时索引、测试索引是否属于原业务审核范围需要先输出清单核对，不能仅靠名称猜测，也不能把当前多个集群的所有索引无条件并入生产任务。首次启用建议限定 `payoneer_olive` 验收；恢复原全索引任务前核对完整目标集合，避免漏掉 PaaS 或引入重复索引。

每轮记录配置路径/摘要、版本、索引/provider、固定资格时间点、计划处理数、实际成功数、冲突数、失败数和剩余待审数。失配、部分失败或超时要呈现失败/部分完成并返回非零退出状态，不能打印笼统“成功”。维护操作不复用线上搜索的空结果兜底。

条件更新不是事务，不能保证任意故障下全有或全无。重跑仍要求 `audit_result=-1`，配合版本冲突保护，不覆盖并发人工审核；需要用并发回归验证这条约束。成功后的剩余统计使用同一轮固定阈值，防止新跨过 24 小时的文档被误判为本轮漏审。

## 验收与上线顺序

1. **隔离实现与离线回归。** 测真实工厂和真实审核规则，只 mock 外部 ES 边界。覆盖路由、ES7/OpenSearch 旧行为、时间边界、质量分支、软删除规则、缺库不创建、干跑零写入、异步 task、超限重试、部分失败/冲突、非零退出及重跑不覆盖人工状态。新增维护能力不改变现有检索调用的默认行为。
2. **main 只读 dry-run。** 解析实际活动配置，确认 Olive→PaaS；新库统计与直接只读聚合一致；日志不再访问旧库。Serverless 也核对至少一个既有业务索引的路由与计数。不能用 dry-run 成功代替写入验收。
3. **写入验收。** 只在当次明确允许的隔离测试索引验证更新/失败恢复及其余字段保真，不借用历史迁移授权写业务数据。必须核验两种 provider 的当前实现。
4. **明确发布指令后启用。** 生产代码按项目规则 git pull，备份并调整定时入口，补审批准范围内的积压，再核对定时运行日志和剩余计数。无需重启检索、挖掘或 Codex 服务。

回退优先停用新增审核入口、保留诊断与写入清单；不能自动恢复为“继续审核旧库”，也不能无条件撤销已经发生的审核字段变化。出现部分写入时记录实际结果，再按明确修复范围处理。

## 交付界限

此次只提出方案，没有实现或生产改动。相关根因与只读实证见 [诊断报告](payoneer_olive_auto_audit_diagnosis_20261019.md)。实施目标是让所有调用方共用引擎配置与数据操作实现，既有审核策略保持不变。
