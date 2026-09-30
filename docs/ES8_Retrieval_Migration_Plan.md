# ES8.17 检索迁移与路由计划

## 当前盘点（只读，2026-09-30）

本计划只记录盘点和后续步骤，本轮没有创建、写入、重建、清空或删除任何索引。

- 新 Serverless 端：服务端返回 Elasticsearch `8.17.0`，集群健康为 green；`/_cat/indices` 返回空集，`test_case` 不存在，因而没有可用于写入回环的 native KNN 索引。该端点仅接受用户提供的 HTTP 入口，HTTPS 9200 的 TLS 握手失败；公网服务必须由独立 TLS 反代保护。
- 新 PaaS 端：白名单放通后已只读核验为 Elasticsearch `8.17.0`，cluster health 为 green（3 节点、36 primary/72 active shards），当前可见 36 个索引全部是 `.kibana`、`.monitoring`、`.internal` 等系统索引；没有业务索引、没有 `test_case`，mapping 中没有 native vector 字段。该端点的 9200 只接受 HTTP，HTTPS 握手失败；公网检索不会直连 ES，后端传输安全限制仍需纳入上线评审。
- 旧源端：旧配置对应的 ES 7.10 服务，发现 342 个索引。旧 `test_case` 存在，但 `indexes.embedding` 是 1024 维、未启用 `index:true` 的 dense vector，不能原地升级或作为 ES8 native KNN 测试索引。
- 旧源中按名称小写后包含 `payoneer` 的索引共 76 个。CAT 的 `docs.count=769,364` 包含 nested 子文档，不能作为根文档迁移量；对 11 个非空索引用 `_count` 得到根文档 263,192 个，其中 `del_flag=0` 为 59,027 个、`del_flag=1` 为 204,165 个。其余 65 个为空或只有约 1.5 KB 的空索引。`payoneer_olive` 和 `payoneer` 等非空索引仍需业务确认是否迁移，不能因为命中规则就直接批量操作。
- sg 临时 canary 已验证两端完整链路：以 `individual_20_payoneer` 的 318 个根文档做首轮 scroll→bulk，两个目标 bulk 失败均为 0，计数和 `del_flag=292/26` 一致；四个 embedding 字段均成功创建 HNSW mapping，代码生成的 root/nested KNN 查询均返回 200。测试索引和测试文档已删除，没有保留生产数据。

## 路由分配清单

本轮目标 PaaS 的实际索引命中清单为空（仅系统索引），Serverless 也为空；下列 76 个名称来自旧源，只是迁移候选和规则命中清单，不代表目标端已存在。

索引名先转换为小写，再按精确规则、通配规则、默认 provider 的顺序解析。当前约定是 `*payoneer* -> paas`，其余索引默认 `serverless`；`payoneer_olive` 已被前者覆盖。下表是旧源只读发现的完整命中清单，全部属于待确认的 PaaS 候选：

```text
payoneer_replay_huting
payoneer_u_reg
payoneer_活动小助手2号
payoneer_olive_neverseen_pf2
payoneer_olive_test_payoneer_olive_test
payoneer_olive_rina
payoneer_olive_emma
payoneer_payoneer_payoneer_3_we_com
replay_0fb44409b83746c188fa48a5099926b0_payoneer_olive_payoneer_olive
payoneer_probe
payoneer_payoneer_activity2_smoke
individual_20_individual_20_payoneer_chloe_marsmind_xiaoma_we_com
payoneer_payoneer_olive
payoneer_olive_neverseen_meta
payoneer_olive_neverseen_cache
payoneer_olive
payoneer_olive_neverseen_pf
payoneer_olive_stacy
replay_e8eb8b49ed354520ad98ae58624d948f_payoneer_olive
payoneer_payoneer_test
payoneer_cs
individual_22_payoneer123
payoneer_olive_u_nk
payoneer_olive_nc3
payoneer_olive_nc2
payoneer_payoneer_payoneer_1_we_com
payoneer_qa_post_6311719
payoneer_olive_neverseen_cat
payoneer_knowledge
payoneer_olive_testu2_1788972165
payoneer_payoneer_scrm_activate2
payoneer_olive_payoneer
individual_20_individual_20_payoneer_chloe_marsmind_1_we_com
payoneer_olive_neverseen_b
payoneer_payoneer
payoneer_7881300404979011
payoneer_olive_neverseen_fix
replay_0fb44409b83746c188fa48a5099926b0_payoneer_olive
payoneer_qa_rc_6311719
payoneer_olive_payoneer_scrm_activate2
customer_platform_payoneer123
payoneer_olive_neverseen_qc
payoneer_olive_neverseen_olv
individual_20_payoneer
payoneer
payoneer_7881303034115541
payoneer_olive_synthcustt20260921t130500
payoneer_olive_neverseen_aonly
payoneer_olive_1688855605344596
payoneer_olive_payoneer_olive
payoneer_olive_test
payoneer_olive_u_smoke
replay_4d9530d4335744b58ad9b71b408a189d_payoneer_olive_payoneer_olive
replay_e8eb8b49ed354520ad98ae58624d948f_payoneer_olive_payoneer_olive
payoneer_olive_helen
payoneer_olive_u_chit
payoneer_olive_u_pin
payoneer_7881300080911295
payoneer_7881300946347501
payoneer_olive_nc
payoneer_macmini-smoke-user-2
payoneer_olive_testuser_1789144399
payoneer_olive_testuser_1788972127
payoneer_kb
payoneer_olive_u_test
payoneer_olive_活动小助手2号
payoneer_qa_whitepaper_5d75ee7
individual_22_payoneer_cs
payoneer_qa_release_smoke_5d75ee7
payoneer_payoneer_payoneer_2_we_com
payoneer_7881302917089111
payoneer_olive_neverseen_olive_chk
replay_4d9530d4335744b58ad9b71b408a189d_payoneer_olive
payoneer_macmini-smoke-user
payoneer_olive_neverseen_p
payoneer_payoneercs
```

有文档的 11 个索引及盘点容量如下；重复 replay 索引保留为独立候选，等待业务确认去留：

| 索引 | CAT docs（含 nested） | 根文档 | del_flag=0 | del_flag=1 | store.size |
|---|---:|---:|---:|---:|---:|
| payoneer_olive | 179446 | 60504 | 13265 | 47239 | 10.6 GB |
| replay_e8eb8b49ed354520ad98ae58624d948f_payoneer_olive | 179164 | 60363 | 13124 | 47239 | 8.9 GB |
| replay_0fb44409b83746c188fa48a5099926b0_payoneer_olive | 179164 | 60363 | 13124 | 47239 | 8.9 GB |
| replay_4d9530d4335744b58ad9b71b408a189d_payoneer_olive | 179268 | 60415 | 13176 | 47239 | 8.9 GB |
| payoneer | 32576 | 15936 | 997 | 14939 | 1.8 GB |
| payoneer_olive_payoneer_olive | 4746 | 1320 | 1260 | 60 | 287.4 MB |
| replay_0fb44409b83746c188fa48a5099926b0_payoneer_olive_payoneer_olive | 4746 | 1320 | 1260 | 60 | 227.2 MB |
| replay_4d9530d4335744b58ad9b71b408a189d_payoneer_olive_payoneer_olive | 4746 | 1320 | 1260 | 60 | 227.2 MB |
| replay_e8eb8b49ed354520ad98ae58624d948f_payoneer_olive_payoneer_olive | 4746 | 1320 | 1260 | 60 | 227.2 MB |
| individual_20_payoneer | 736 | 318 | 292 | 26 | 47 MB |
| payoneer_payoneer | 26 | 13 | 9 | 4 | 1.8 MB |

根文档和 `del_flag` 分布来自只读 `_count`/terms aggregation；迁移校验必须使用这个口径，不能直接复用 CAT 数字。`del_flag=1` 的记录先保留，除非业务明确批准清理。

## 目标 mapping 与迁移步骤

### 目标结构和索引范围

- 路由规则仍是索引名小写后 `*payoneer* -> paas`，其余业务索引 -> `serverless`。本次 76 个命中项全部只是候选清单，不代表全部都要创建目标索引。
- 先由业务确认 manifest：生产索引、replay 副本、测试/探针索引、空索引分别列出 owner、用途、保留期和是否迁移。默认先迁移已确认的生产索引；replay、`*_test*`、`*_smoke*`、`probe` 及 65 个空索引不自动迁移。
- 目标采用物理索引名 `<source>__v817_<batch>`，迁移完成后在目标集群建立同名 alias。这样可以保留旧源和目标两套物理索引，切换只是 alias/路由变更，回滚不需要覆盖数据。
- 目标 mapping 必须先在空索引上创建并预检：`title_embedding`、`content_embedding`、`indexes.embedding`、`image_indexes.embedding` 四个向量字段全部为 `dense_vector(dims=1024,index=true,similarity=cosine,index_options.type=hnsw)`；后两个字段所在对象为 `nested`。`title`、`content` 使用目标端已确认存在的 analyzer，`del_flag` 为 integer。若目标端没有 `ik_max_word`，必须先用 `_analyze` 和 canary 索引确定替代 analyzer 并做检索回归，不能在迁移时临时失败。
- 创建前逐个获批源索引保存完整 mapping/settings/templates/aliases，做字段兼容 diff（dynamic、date format、keyword、object/nested、`ignore_above`、`_source` 和未知字段）；不能只复制几个字段后假定旧 `_source` 一定可写入。目标容量按根文档、嵌套向量数量、向量字节、segment、replica 和增长率估算并留 headroom；不直接套用当前 engine 的固定 `3 primary + 1 replica`。
- 目标写入前必须分别验证 source 的 metadata/read/scroll 权限，以及 target 的 create/mapping/bulk/refresh/alias/cluster-monitor 权限。当前只有只读探测，这些写权限与容量检查尚未完成。

### 执行顺序

1. **预检和冻结清单**：保存每个源索引完整 mapping、settings、templates、aliases、权限结果和根文档/删除标记分布；确认目标配额、容量、分片上限和写入权限。建立可复现 manifest（源/目标名、mapping hash、计数、ID 分片 hash、向量模型/维度、owner、批准人）。
2. **目标能力 canary**：经授权后，用临时索引验证 analyzer、native HNSW、nested KNN、过滤、bulk、refresh、alias 和权限；该 canary 通过前不触碰业务索引。当前目标为空，尚未执行这一步。
3. **创建目标索引**：在目标 provider 创建带 `__v817_<batch>` 后缀的物理索引、mapping、经容量计算的分片/副本和 refresh 策略；不能盲用固定 `3 primary + 1 replica`。
4. **首轮批量迁移**：当前两个目标是独立 HTTP 端点，不能假定 `_reindex` 的 remote source 已被白名单和权限放通。实际执行使用 sg 上的受控迁移进程，对每个获批索引只做一次源端 scroll（ES7 若不支持 PIT 就不用 PIT；批次不超过 500 条、单请求不超过 20 MB），读取 `_source`，保留原 `_id` 和全部业务字段，直接 bulk 到目标；不落 Mac 或单机全量文件。首轮完成后记录开始/结束时间、源端最大 `update_time` 和 checkpoint，后续不再重复做全量查询。
5. **向量和异常处理**：逐条检查 `indexes.embedding`/`image_indexes.embedding` 的维度、NaN 和零向量；维度为 1024 且模型一致时直接复用向量，缺失、维度不符或模型不一致的文档进入重算队列，不能静默丢弃或混用模型。bulk 使用幂等 `_id`，记录 checkpoint（索引、slice、scroll/search_after 游标、批次、目标 ack）、失败 ID/DLQ、错误和重试次数；自写 bulk 显式设置并发、字节/条数上限、refresh 策略和退避，遇到 429/5xx 重试。
6. **增量追平**：先做一次完整批量迁移，记录每个索引的 `snapshot_started_at`、`snapshot_finished_at`、源端最大 `update_time` 和迁移 checkpoint；这次完成后不再重复查询旧 ES 做全量同步。后续只同步该水位之后的新增/更新，硬删除必须来自包含 delete 的 CDC/变更日志；若没有可靠删除日志，则在停写窗口做最终一致性重扫。`update_time` 只作为水位，不能单独证明没有硬删除或秒级碰撞。迁移工具不自动修改源端写入状态。
7. **完整校验**：对源/目标分别比较根文档总数、`del_flag`/`data_type`/`audit_result` 分组计数和 nested 子文档计数；流式按 `_id` 比较 canonical `_source` hash，报告 missing、extra、mismatch；计算稳定分片 ID hash，抽查 `title`、`content`、`synonyms_title`、`indexes.text`、向量维度/NaN/模型元数据。bulk failures 必须为 0 并完成 refresh 后，再用固定 gold query 集合验证 BM25、native nested KNN、双路合并、`del_flag` 过滤、分页和排序，记录结果 ID overlap、召回@k 和延迟。
8. **灰度和切换**：先将一个已校验索引的读取路由切到目标 alias，做 smoke 和监控；再按 manifest 批次扩大。切换记录路由版本和时间，旧服务/旧源保持可读。
9. **回滚和收尾**：若计数/hash 有差异、bulk 出现未重试成功的失败、召回@k 或结果 overlap 低于 gold 基线、错误率/延迟超过阈值，则停止扩大并把路由切回旧读取路径；保留源索引、目标 `__v817_<batch>` 索引和 checkpoint。稳定观察期结束后，由业务批准旧索引归档；迁移程序不执行删除。

### 建议批次

| 批次 | 范围 | 目的 |
|---|---|---|
| C0 | 1 个获批的小索引（优先 `individual_20_payoneer`） | 验证 mapping、analyzer、HNSW、bulk 和校验流程 |
| C1 | `payoneer_olive` | 验证最大生产索引的吞吐、容量和召回 |
| C2 | `payoneer` | 验证第二个生产索引并完成路由灰度 |
| C3 | 其余已确认的非空业务索引 | 按 owner 和容量限流迁移 |
| C4 | replay/测试/空索引 | 仅在 owner 明确批准后迁移；否则保留源端 |

## 当前阻塞与验收边界

- PaaS 端已验证为 ES8.17.0；正式业务索引尚未迁移。临时 canary 已验证 create/mapping/bulk/refresh/alias/delete 和 HNSW KNN，生产容量、配额和每个业务索引的写权限仍需单独确认；PaaS 只支持 HTTP 传输。
- Serverless 正式业务端仍为空，且只提供 HTTP；没有 `test_case` 或其它现成业务索引。临时 canary 已验证四个 embedding 字段和 native KNN，测试索引已删除。
- 当前代码没有跨集群迁移器、checkpoint/manifest、DLQ 或 delta 组件；迁移应另做独立的 dry-run/执行命令，默认不得自动 create、clear、delete 或写入真实 `test_case`。
- 重构服务的 `/search` 与 `/web_search` 已实现并通过离线契约测试；公网入口需在运行环境使用 TLS 反代和 Basic 认证，写入/删除路由不挂到该公开路径。

## 当前部署验收

- 提交链：`63d8385`（检索 API）+ `5ab22d5`（检索进程隔离）+ `8552b95`（本盘点更新）。运行工作区已通过 `git pull --ff-only` 接收。
- systemd：`kdb-forge-retrieval.service`，监听 `127.0.0.1:8012`，运行 `.venv-es817` 的 `elasticsearch 8.17.2` 客户端；日志为 `/root/kdb-forge/logs/uvicorn_search_8012.log`。
- 公网入口：`https://api.marsmind.co/kdb-search/health`、`https://api.marsmind.co/kdb-search/search`、`https://api.marsmind.co/kdb-search/web_search`。入口复用现有 TLS，检索路由使用独立 HTTP Basic；检索进程没有写入/删除路由。
- 实测：公网 `/health` 返回 200；未认证 `/search` 返回 401；认证 `/search` 与 `/web_search` 均到达 ES8.17 后端，但因 `test_case` 在两个新集群均不存在而返回 503。该结果证明入口、鉴权、ES8 客户端和错误边界可用，不代表已有业务数据的召回验收。
