# main 新 ES8 引擎扩大只读测试，2026-10-08

用户授权扩大新引擎测试，新 ES 尚未正式使用；同时沿用“不要影响 main 在线服务”的约束。本轮已完成 37 组样本、148 次真实双路检索，正常返回的 592 个原生 ES 查询均无 HTTP 错误、分片失败或超时。111 次相对首轮的重复查询，候选集合与最终 Top5 顺序全部一致；类目与软删除条件未观察到越界。**测试运行完成，但引擎完整验收仍有两项问题，不能标为全部通过。**

测试源码来自旧项目 `/root/knowledge_database_builder`，分支 `main`，HEAD `a36efc7245dedf2492f5be396f87390885f3a4f4`，加既有未提交改动。实际引擎 SHA256：`8b773057ecc41da40fc5d87eb1afc1bc21ecc4c8a9a8a23f27c6b17f69dc7343`。业务层 SHA256：`509ec93d1b5e1c47391063af65304aebedd833180a5051e43d34a6c267b84b27`。未加载隔离开发目录尚未合入的另一份引擎，也没有用重构项目实现替换旧项目。`/root/kdb-forge/.venv-es817/bin/python` 仅作为 sg 准备工具的已有解释器；应用源码和实际执行的引擎来自上述旧目录。

## 执行范围和计时口径

- main：现有 SSH 目标 `shenzhen-120`，120.77.147.247。单个 nice 15 进程，标准库 Python3.12，最大 4 个工作线程；源码和连接信息由 SSH stdin 加密传入内存，不在 main 写应用文件或安装依赖，不开监听端口。
- 仅连接新 ES8.17.0，两种部署均先验版本和精确索引存在。4 个既有物理索引：`mercado_local_mercado_local_admin`、`mercado_local`、`payoneer_olive_payoneer_olive`、`payoneer_olive`。没有别名或版本后缀转换，未查询旧 ES7。
- 37 组样本 = 12 个已保存历史问题/QA 标题控制 + 25 个已保存类目组合；Local 15 组、Olive 22 组。包含父子类目、两子类 OR、路径/ID 矛盾、空 ID 列表等。4 个反例每阶段均应无命中。
- 执行真实当前 `IndexClientRouter`、`EsSearchInterfaceES8.__init__ / search_multi`、native KNN 构造、双路召回和合并逻辑；公私库每索引每路 5 条，每次逻辑检索 4 个 ES 请求。构造器仅在测试进程内关闭 ensure/mapping，正式配置文件没有改变。HTTP adapter 注入现有 client_factory 边界，按实际引擎参数发送原 DSL，不修改查询或裁剪外层 source。
- 使用未改动业务 `_cal_title_similarity / _cal_similarity` 的源代码提取体，启用 QA 和同义问法重排。main 没有 numpy，余弦数值边界采用相同公式的标准库 double 计算；随机1024维对照 numpy 误差小于 `1e-12`、零范数约定一致。其耗时不等于生产 numpy 的耗时。
- 24 个不同 query 的向量在 sg 用既有 AliEmbedding 分3批预生成并复用，未计入检索时间。`engine_ms` 包含 4 个原生请求的传输、完整 JSON 解析和引擎合并，重排另计；闭环吞吐包含测试线程初始化、引擎与重排。本轮没有执行完整 `/search` HTTP 服务、URL渲染、LLM或请求现场 embedding。
- 完整 source 保留根/嵌套向量，正常148次检索合计响应约169.1MB（161.3MiB）。性能数据来自只读 HTTP adapter，不能当作正式 ES8 Python transport 或完整应用接口的最终容量验收。

## 实际耗时和吞吐

P50/P95 使用 nearest rank；各平台样本只有15/22组，P95受单条波动影响。并发阶段复用相同问题，首轮与后续服务端缓存/负载条件不同，不能把全部提升归因于并发。

| 并发线程 | 逻辑检索次数 | 实际阶段时长 | 闭环逻辑吞吐 | Local 引擎 P50 / P95 | Olive 引擎 P50 / P95 |
|---|---:|---:|---:|---:|---:|
| 1 | 37 | 15.65秒 | 2.36次/秒 | 135 / 340ms | 111 / 1941ms |
| 2 | 37 | 3.74秒 | 9.91次/秒 | 145 / 260ms | 102 / 390ms |
| 4 | 74 | 6.01秒 | 12.32次/秒 | 221 / 949ms | 124 / 453ms |

这是包含公私库双路和本地重排的短时间闭环测试，不是持续10QPS的外部到达流量测试。阶段2/4 ES原生请求吞吐约39.6/49.3次每秒，**不是**39.6/49.3个业务查询每秒。4并发Local尾延迟上升明显，不能只报吞吐而不报P95。

首轮 Olive 历史问题 H1 最慢3956ms，其中公库向量路 HTTP 3373ms、ES `took=3358ms`；H2公库向量路 HTTP1694ms、took1676ms。这些慢样本主要耗在 ES 内部，不能全部归因 sg 到深圳网络。它们是首轮观察，不是通过重启/清缓存制造的冷启动实验。4并发Local最慢1024ms，同次各路took仅5/8/19/16ms，完整传输和客户端环节在尾延迟中也占较大份额，未继续推断为某个已测明的网络故障。

## 正确性检查与仍有问题

| 检查 | 实际结果 | 状态/边界 |
|---|---|---|
| HTTP / shards / timeout | 592个搜索均成功，0分片失败、0超时 | 本批通过 |
| 类目、audit、data_type、del_flag | 148次结果按独立 source oracle 检查，0越界 | 本批通过；只涵盖这些真实输入 |
| 无命中反例 | 16次均为空；33组正例每次均有候选 | 本批通过 |
| 重复召回集合/Top5顺序 | 111/111一致 | 本批通过；未据此证明其他数据或query的等价质量 |
| 返回字段形状/已有向量维度 | 0已检出形状或维度错误 | 保留完整外层source；没有裁向量换速度 |
| inner_hits内部source | 1448个inner hit全为空 | **当前引擎已知请求缺陷仍在**，见下文 |
| 同义问法重排输入 | 20次文档出现次数缺输入，集中1个真实文档 | **数据对应关系有缺口**，见下文；非20个不同文档 |

**D01：inner_hits请求字段过滤仍错误。** 当前源码 `knowledge_interface_tools/es8_search_interface.py:491` 使用相对 `text / embedding`，请求需按 nested path 限定。追加9个低负载新ES只读请求（sg执行，不计main耗时）实际对照：

| 部署 | 当前相对 includes | 仅诊断请求改为 `indexes.text / indexes.embedding` |
|---|---|---|
| Serverless，mercado_local | 9个内部source空，0维 | 同样9个内部source非空，均1024维 |
| PaaS，payoneer_olive | 11个内部source空，0维 | 同样11个内部source非空，均1024维 |

两个版本请求各命中5条、分片失败0。不是服务端不支持向量，也不是存储必然没有向量。此问题此前10/05报告已有，本轮再次确认当前旧目录源码没有合入隔离开发版本的修复。隔离目录 `/root/knowledge_database_builder-es8-dev` 现有引擎 hash `07d08eb5daa3daccb87b5297f43c30f9b507713cf978567fa5b8f555a9b1291e`，其约634行已使用完整路径，但本轮未替换/部署该实现，也没有重新验收其余改动。当前全外层source仍提供嵌套向量，因此本批实际重排没有因此丢向量；未来不能在过滤修正前恢复外层向量裁剪。本轮未改引擎让测试通过。

**D02：一条Local文档的synonyms_title与indexes不对应。** 在上述5个串行异常样本候选中，追加mget检查50个Local文档和1个Olive文档。只有 `mercado_local / 40a7cc9937550aaa44ba5979ed0b47d1` 出现：15个同义问法、indexes只有1项、文本交集为0；这1项及根title/content向量均1024维。正常148次检索中，它出现在5个问题×4轮，共20次。实际业务约 `search_index_data_interface.py:1387` 只有索引文本属于synonyms_title才参与同义重排，因此这些15个问法没有对应向量输入，标题/正文重排仍可用。它是存储文档的对应关系缺口，不能靠D01过滤修复补出不存在的15项。本地MEMORY记载它是2026-09-01的人工聚合QA；本轮未查询旧库或比较历史导出，因此不宣称是本次迁移漏项，也未自动补向量/更新文档。完整来源判断及补数应另做，不把“1项已有向量”当成“15个同义向量齐全”。

## 在线保护和实际请求数

main在线检索PID307354、启动ticks1688243718、工作目录与源文件hash前后完全一致。load1测试前0.72、完成后0.73，阶段内记录最高0.85，8CPU；MemAvailable最低20.63GiB。4并发阶段整个测试进程CPU累计4.54秒、墙钟6.01秒，约使用0.76CPU平均值，并不意味着测试没消耗资源。没有启动/停止/重启服务、git拉取、部署、配置/索引/文档/mapping/alias写入，也没有调用任何在线检索HTTP接口。sg现有服务PID3751589/3751674同样保持原启动时间；未接触迁移程序。

低优先级、每次只取5条/路、最大4线程、请求总预算、host load与空闲内存及PID保护均生效；遇到首次真实请求/分片错误即停止，没有发送重试风暴。没有在线API P95观测，因此“未变更在线服务且主机负载较低”不等于证明在线性能影响绝对为零。

实际本轮总计：

- 成功main轮：592search +20版本/存在性预检与工作线程连接预热 =612次ES读。
- 初次测试工具护栏过严，误把nested inner_hits._source也当成外层裁剪拒绝；仅1search成功发出、共9次ES读后停止。这是测试工具错误，修正护栏并离线验证后使用独立run2目录执行，原失败证据完整保留，不算引擎缺陷。
- 追加sg诊断：2版本GET +3mget +4search =9次ES读，检查51个文档；没有额外embedding。
- 合计630次新ES只读请求；两次准备各3次embedding batch，共6次调用/48条文本计算（每轮24个不同query），没有LLM调用。没有旧ES读，也没有ES写。

## 工具、命令和证据

新增工具和对应schema，先写/读schema再实现。源实现/运行配置未修改；不提交、推送、部署或重启。工具语法/内嵌代码检查、标准库余弦对numpy、HTTP适配器允许合法inner_hits过滤且拒绝外层裁剪的离线边界检查均通过；这些不冒充真实ES写入或完整API验收。本轮没有重复计入历史pytest数量。

```bash
env -C /root/knowledge_database_builder \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/root/knowledge_database_builder:/root/knowledge_database_builder/tests \
  KDB_ES8_PROBE_OUTPUT=/root/knowledge_database_builder/docs/reviews/main_es817_expanded_20261008_run2 \
  /root/kdb-forge/.venv-es817/bin/python -u tests/main_es817_expanded_20261008.py

env -C /root/knowledge_database_builder \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/root/knowledge_database_builder:/root/knowledge_database_builder/tests \
  /root/kdb-forge/.venv-es817/bin/python tests/main_es817_response_diagnose_20261008.py
```

证据目录0700、文件0600；没有保存真实向量数值、知识原文、query明文或连接凭据。性能工具再运行须指定新的输出目录，不覆盖既有证据。诊断工具固定引用run2，重跑应先建立新的诊断schema/输出目标，不覆盖原文件。

- [main逐次指标/ID/前后进程元数据](/root/knowledge_database_builder/docs/reviews/main_es817_expanded_20261008_run2/evidence.json)
- [性能及条件汇总](/root/knowledge_database_builder/docs/reviews/main_es817_expanded_20261008_run2/summary.json)
- [真实source/字段过滤A/B诊断](/root/knowledge_database_builder/docs/reviews/main_es817_expanded_20261008_run2/response_diagnosis.json)
- [执行清单/源码与工具hash](/root/knowledge_database_builder/docs/reviews/main_es817_expanded_20261008_run2/manifest.json)
- [扩展性能工具](/root/knowledge_database_builder/tests/main_es817_expanded_20261008.py)、[只读诊断工具](/root/knowledge_database_builder/tests/main_es817_response_diagnose_20261008.py)
- 初次工具停止证据保留在 `docs/reviews/main_es817_expanded_20261008/`，不与成功轮混算。

尚未验证：长期10QPS/持续尾延迟、任意大top_k或全量分页、图像向量、完整service传输与现场embedding、不同provider混合查询、大数据变更下稳定性、固定相关性标注集与正式ES8 Python客户端运行时的性能。当前短测支持“这组QA输入在main可达到约12次/秒且结果稳定”，不支持“全部契约/检索质量/上线容量已经验收”。
