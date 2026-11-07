# 120 旧项目 ES8 线上配置与发布准备

> 本文保留发布前的历史准备快照，下面的“未上线/未推送/未执行”不是当前状态。用户随后明确授权发布，120已完成git pull、配置切换及两服务启动；当前状态、实际日志入口、启动与回退命令见 [上线记录](es817_online_deployment_20261009.md)。

截至2026-10-09，本轮**尚未上线、未切换在线配置、未重启服务**。用户授权上线120的旧检索与挖掘服务，并要求对齐线上配置和快速回退；不能把准备完成称作已上线。本轮还没有commit/push；远端main仍为早期ES8提交，不包含本候选全部修复。按用户既定规则，生产源码必须在目标目录git pull，不能直接覆盖。

## 已准备的实际线上文件

目标SSH `shenzhen-120`，目录 `/root/knowledge_database_builder`。原线上检索默认和离线业务配置实际指向 `/root/dify/knowledge_database_builder/config/config_es_engine.json`。没有修改该共享文件。下列业务候选只改search_engine_config_path，embedding、相似度、类目、LLM、去重参数保持逐项一致：

- 待启用引擎配置：`/root/knowledge_database_builder/config/config_es_engine_es817.online.json`，0600。
- 业务候选：`backup/es817_release_20261009/config/config_for_search_index.json.es817.candidate`及`config_for_search_index_no_dup_payoneer.json.es817.candidate`。
- canonical版本8.17，原默认物理名open_shop，indexes_embedding1024；default Serverless，既有payoneer*与*payoneer*规则选PaaS；dual、ensure_index_on_init=True、auto_update_mapping=False。
- 固定86业务库原名不改，不通过内部旧名→staging映射；open_shop旧库原生统计0文档，新端不存在，后续正常初始化会创建空默认库，不能称作漏了有数据的默认库。

线上活动的两份业务配置目前仍为原字节，父进程检索307354、挖掘2269292未改。挖掘/health复验active_tasks=0、queue_size=0，实际max_concurrency=2；切换时需重新查询，而非沿用本次空闲状态。

## 环境与代码候选

120原名py38实际上Python3.9.0，Elasticsearch7.10.0。保留不变，新建独立 `.venv-es817`（system-site-packages复用既有业务依赖），仅在该环境安装ES8.17.2/elastic-transport8.19.0。新旧环境真实分别输出8.17.2及7.10.0；没有全局pip升级。新挖掘父进程需同用新解释器并把新venv/bin放PATH首位，确保子进程sys.executable及PATH python均选ES8，不仅换检索进程。

发布开发目录 `/root/knowledge_database_builder-es817-release-20261009`，detached HEAD基线a36efc7245dedf2492f5be396f87390885f3a4f4。仅选取已测试隔离集成的当前旧项目源码、测试及对应schema，不碰原服务checkout脏改动；复制后的核心hash与已有集成一致：

| 核心文件 | SHA256 |
|---|---|
| es8_search_interface.py |d9a30277f6464d639a9255800506f8bc9fffeff062834e10cd1839d1df4cd9fc|
| es_search_interface.py |1aaebeaf53587f4e9e585fb908d09318c0a0be636eb4f36b8076517fb5c739e7|
| search_index_data_interface.py |509ec93d1b5e1c47391063af65304aebedd833180a5051e43d34a6c267b84b27|
| es8_client_router.py（基线原有未改） |3570d825d5cdd660b23eeb8bbc53befd32b39a8def0195444a7318d64a5470ce|
| es_count_utils.py |0a4d82e166f98cb382fe39ecebed52156e7bcabc02870ba3f073471b4d229e78|
| knowledge_database_search_es.py |a14d1431568a399a4124c1f6817cec849259892dcdbab9137a6b86b4f12eda6b|

范围：当前原HTTP ext_info保真、缺失私库正常自动建立/公库容错、授权新增get_from_type_count、Serverless条件更新和文件软删除完整source/PIT/CAS适配。当前候选没有集成后来test_case验证的native pipeline方案；不能把平台原生试验称作当前生产实现。广泛审计checkout中的其它修复仍与本最小集成不同，不能宣称全部R01-R14或公开复杂契约都已验收。

120 HEAD7ca77d71f82f5dbeb8ad75caf234550421bb35a7，tracked clean，已有大量untracked保留。只执行了git fetch，origin/main为a36efc7245dedf2492f5be396f87390885f3a4f4，确认可快进。未git pull、未覆盖源码、未stash/reset/clean。发布前仍须复验新候选与目标untracked路径碰撞。

## 实际验证

发布checkout重跑同集成测试命令：**300 passed、2 xfailed、417 warnings、7.59s**。日志 `es817_release_tests_20261009.log`、JUnit同名xml。xfail保留O01离线单条处理失败仍正常退出（用户暂缓）和O03未用示例es8.17版本别名拒绝；线上配置使用canonical8.17。没有把xfail当通过或全CRUD完整验收。

在120的独立Python进程，内存加载候选源码，没有覆盖生产文件或启动服务。真实factory+真实ES8类对两库match_none strict count均0且正常；候选业务、检索服务和挖掘服务模块在ES8新环境及原ES7环境均成功导入。这是环境及只读入口验证，未执行服务lifespan或完整离线任务。见 `es817_release_imports_20261009.json`。

少量真实只读样本向量/KNN：mercado_local2条、Olive2条，全部有1024维nested向量；目标stored source未过滤。响应分别1,098,079与485,632字节，单次127.3ms及5748.8ms；单样本不能算性能验收，也没有据此更改候选预算或源字段。证据 `es817_release_runtime_readonly_20261009.json`。未进行当前版本真实业务写或公网CRUD请求。

回退工具实际隔离9项通过，使用SG现有py38/psutil环境：`/root/miniconda3/envs/py38/bin/python -m pytest -q tests/test_es817_online_rollback_20261009.py -p no:cacheprovider --tb=short`，9passed/0.14s。首两次诊断环境缺psutil，测试import失败，改用已安装psutil的原py38环境，不修改实现或全局依赖来遮掩。工具的真实停止/恢复分支尚未演练；不能称线上回退已实测。

## 快速回退准备

完整私有备份：`/root/knowledge_database_builder/backup/es817_release_20261009`（0700），配置0600，保存原业务配置、root原engine及实际引用的共享legacy engine、配置SHA、原启动参数、git状态。操作辅助脚本 `rollback_legacy.py`只置于该backup，不覆盖生产业务源码；schema及源码在发布checkout的scripts/ops。

切换完成时必须写 `activated.json`：准确记录两个新父PID、create_time、cmdline、解释器和所有活动配置SHA。缺此journal回退工具只报告not_activated并不停止现有旧服务。默认检查：

```bash
/root/miniconda3/envs/py38/bin/python \
 /root/knowledge_database_builder/backup/es817_release_20261009/rollback_legacy.py
```

真正回退（当前不要执行，尚未切换）：

```bash
/root/miniconda3/envs/py38/bin/python \
 /root/knowledge_database_builder/backup/es817_release_20261009/rollback_legacy.py --execute
```

只检查/停止journal精确登记的两父进程，防PID复用；挖掘有任务/排队则拒绝。校验备份及共享legacy引擎，优雅SIGTERM，等待≤60秒不SIGKILL；原子恢复原配置，用未改的py38及原参数启动两服务，记录新PID/日志，验证8003 openapi和6000 health。中途失败保留phase与PID，不重复启动；不reset源码、不删除数据、不触碰其它服务。代码和数据回退不是一回事：配置回退不能反向同步切换后新库写入，写入切换后需要另外核对变更。

## 切换前未完成

修复尚未在远端main，必须先明确本轮发布提交/push权限，才可按目标工作目录git pull规则上线。不能拉早期a36便称修复已部署，也不能用scp覆盖引擎绕过规则。

数据补差仍未真实执行：固定86新库净少213；joint_login一条与mercado两条del_flag不一致。已向用户先报告；后台agent继续PaaS lineage及有界候选/dry-run准备，真实写保持0。上次81指纹通过并不替代今天全字段验收。完整补差和异常处置未完成之前保持原线上配置。

后续上线顺序：确认并发布本候选→120 git pull --ff-only并核对源码hash/环境→完成已授权补差及标记验收→重新核对挖掘空闲→原子切换两份实际业务配置→精准重启两服务并登记activation→低负载只读/search、/web_search、/get_from_type_count及离线进程路径验收。不能启动任意业务写探针来代替此前明确授权测试范围。
