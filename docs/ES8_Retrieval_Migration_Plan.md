# ES8.17 检索迁移与路由计划

## 当前盘点（只读，2026-09-30）

本计划只记录盘点和后续步骤，本轮没有创建、写入、重建、清空或删除任何索引。

- 新 Serverless 端：服务端返回 Elasticsearch `8.17.0`，集群健康为 green；`/_cat/indices` 返回空集，`test_case` 不存在，因而没有可用于写入回环的 native KNN 索引。该端点仅接受用户提供的 HTTP 入口，HTTPS 9200 的 TLS 握手失败；公网服务必须由独立 TLS 反代保护。
- 新 PaaS 端：白名单放通后已只读核验为 Elasticsearch `8.17.0`，cluster health 为 green（3 节点、36 primary/72 active shards），当前可见 36 个索引全部是 `.kibana`、`.monitoring`、`.internal` 等系统索引；没有业务索引、没有 `test_case`，mapping 中没有 native vector 字段。该端点的 9200 只接受 HTTP，HTTPS 握手失败；公网检索不会直连 ES，后端传输安全限制仍需纳入上线评审。
- 旧源端：旧配置对应的 ES 7.10 服务，发现 342 个索引。旧 `test_case` 存在，但 `indexes.embedding` 是 1024 维、未启用 `index:true` 的 dense vector，不能原地升级或作为 ES8 native KNN 测试索引。
- 旧源中按名称小写后包含 `payoneer` 的索引共 76 个，合计 `docs.count=769,364`；其中 11 个有文档，其余 65 个为空或只有约 1.5 KB 的空索引。`payoneer_olive` 和 `payoneer` 等非空索引仍需业务确认是否迁移，不能因为命中规则就直接批量操作。

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

| 索引 | 文档数 | 大小 |
|---|---:|---:|
| payoneer_olive | 179446 | 10.6 GB |
| replay_e8eb8b49ed354520ad98ae58624d948f_payoneer_olive | 179164 | 8.9 GB |
| replay_0fb44409b83746c188fa48a5099926b0_payoneer_olive | 179164 | 8.9 GB |
| replay_4d9530d4335744b58ad9b71b408a189d_payoneer_olive | 179268 | 8.9 GB |
| payoneer | 32576 | 1.8 GB |
| payoneer_olive_payoneer_olive | 4746 | 287.4 MB |
| replay_0fb44409b83746c188fa48a5099926b0_payoneer_olive_payoneer_olive | 4746 | 227.2 MB |
| replay_4d9530d4335744b58ad9b71b408a189d_payoneer_olive_payoneer_olive | 4746 | 227.2 MB |
| replay_e8eb8b49ed354520ad98ae58624d948f_payoneer_olive_payoneer_olive | 4746 | 227.2 MB |
| individual_20_payoneer | 736 | 47 MB |
| payoneer_payoneer | 26 | 1.8 MB |

## 目标 mapping 与迁移步骤

1. 先恢复 PaaS 网络访问，读取两端版本、权限、alias、索引容量、mapping、向量维度和删除标记分布；对 76 个命中项逐项确认，不将空索引和 replay 副本自动纳入。
2. 为每个获批目标创建新的 ES8.17 索引，沿用业务字段语义；`indexes` 和 `image_indexes` 使用 nested，`embedding` 使用 `dense_vector`、`dims=1024`、`index=true`、`similarity=cosine`、`index_options.type=hnsw`。旧根向量保留为兼容字段，但不把未索引旧向量当作 native KNN。
3. 在 ES 集群内优先使用 `_reindex` 或受控 scroll/bulk 流式迁移，设置 `requests_per_second`、批量上限和断点状态；不把全量文档下载到 Mac 或单机磁盘。可复用且维度和模型一致的 `indexes[].embedding` 直接复制，只有缺失、维度不符或文本/模型不一致时才排入重算队列。
4. 迁移期间保存每批 checkpoint、失败文档 ID 和重试次数；按 `_id` 幂等写入，bulk 部分失败可重试，源索引保持只读快照或保留版本。先迁移小规模获批索引做 mapping、字段和向量抽样校验，再扩大批量。
5. 以源/目标文档总数、按 `del_flag`/`data_type`/`audit_result` 分组计数和抽样字段 hash 做校验；随机抽查 `title`、`content`、`synonyms_title`、`indexes.text` 与向量维度。用同一 query 集合分别验证 BM25、native KNN、双路合并、过滤、分页和分数排序。
6. 增量追平按 `update_time` 或源端变更日志执行，完成停写窗口最后一轮增量、计数和检索回归；灰度阶段把路由指向新索引，保留旧索引与回滚路由。确认稳定后再由业务批准旧索引归档，迁移脚本不自动删除。

## 当前阻塞与验收边界

- PaaS 端已恢复只读连通并验证为 ES8.17.0，但只有系统索引；旧源的业务索引尚未迁移，且 PaaS 只支持 HTTP 传输。
- Serverless 新端为空，且只提供 HTTP；没有 `test_case` 或其它现成 native KNN 索引，因此本轮没有真实 ES8 检索命中验证，也没有写入测试数据。
- 重构服务的 `/search` 与 `/web_search` 已实现并通过离线契约测试；公网入口需在运行环境使用 TLS 反代和 Basic 认证，写入/删除路由不挂到该公开路径。

## 当前部署验收

- 提交链：`63d8385`（检索 API）+ `5ab22d5`（检索进程隔离）+ `8552b95`（本盘点更新）。运行工作区已通过 `git pull --ff-only` 接收。
- systemd：`kdb-forge-retrieval.service`，监听 `127.0.0.1:8012`，运行 `.venv-es817` 的 `elasticsearch 8.17.2` 客户端；日志为 `/root/kdb-forge/logs/uvicorn_search_8012.log`。
- 公网入口：`https://api.marsmind.co/kdb-search/health`、`https://api.marsmind.co/kdb-search/search`、`https://api.marsmind.co/kdb-search/web_search`。入口复用现有 TLS，检索路由使用独立 HTTP Basic；检索进程没有写入/删除路由。
- 实测：公网 `/health` 返回 200；未认证 `/search` 返回 401；认证 `/search` 与 `/web_search` 均到达 ES8.17 后端，但因 `test_case` 在两个新集群均不存在而返回 503。该结果证明入口、鉴权、ES8 客户端和错误边界可用，不代表已有业务数据的召回验收。
