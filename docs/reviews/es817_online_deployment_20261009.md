# 120 旧项目已发布及线上配置切换，2026-10-09

用户明确“发布并上线，最主要配置改好”；已完成。120目录 `/root/knowledge_database_builder`，main通过 **git pull --ff-only** 从7ca77d71更新至 **3ee7f931d4ad598a54173bb2881a36f0a26a3112**。两次发布提交0ae31805（实现/schema/测试）及3ee7f931（验证日志、测试文件末尾格式）均已推送main，未覆盖生产业务源码、未reset/stash/clean或提交既有配置/数据/临时脚本。

活动配置 `config/config_for_search_index.json`、`config/config_for_search_index_no_dup_payoneer.json` 已原子切换到 `/root/knowledge_database_builder/config/config_es_engine_es817.online.json`。仅业务engine路径改变，其余embedding、相似度、类目、LLM和去重参数逐项保留。engine版本canonical8.17、原名open_shop、1024维、既有Serverless/PaaS路由、ensure=True/autoMapping=False。共享 `/root/dify/.../config_es_engine.json` 没有修改。

两个原服务在挖掘active_tasks=0/queue_size=0且精确PID/创建时间/cwd/命令全部吻合之后优雅停止；没有kill其它进程。新服务均从旧项目 **.venv-es817/bin/python** 启动，PATH首位也为该目录，挖掘后续PATH python和sys.executable均使用ES8.17.2。原py38（实际Python3.9、ES7.10）完整保留。

安装基于 `/root/miniconda3/envs/py38/bin/python` 用 `venv --system-site-packages` 创建旧项目的独立环境，复用既有业务依赖，只在venv安装ES8客户端。上线后再次实测Python3.9.0、elasticsearch8.17.2、elastic-transport8.19.0，客户端实际位于 `.venv-es817/lib/python3.9/site-packages/elasticsearch`；pyvenv.cfg确认base为原py38且system-site-packages=true，原环境仍为elasticsearch7.10.0。启动命令不能换回原py38的裸python；也不要用原ES7 requirements在新venv覆盖客户端。

| 服务 | 新父PID | 端口 | 真实状态 |
|---|---:|---:|---|
| 旧检索 |1585100|8003|openapi成功，含get_from_type_count，4工作进程|
| 旧挖掘 |1533339|6000|health成功，active/queue0，实际max_concurrency2保持|

初次切换检索父PID为1533338；01:27复查发现其已替换为1585100，无法仅凭当前进程断言是谁执行的重启。当前精确cwd/参数/解释器/PATH/日志stdout均再次验证，两个端口正常；没有为此再重启。原activation保留为私有 `activated.initial_release.json`，活动journal原子更新为当前精确身份并补充ES8 engine配置SHA，回退check再次返回ready、停止0服务。公开观察证据 `observed_current_services_20261009.json`；current_log_entries.json保留初次检查快照。目录HEAD后来c84b6120只增加上线文档，核心引擎SHA未变。

日志位于 `log/es_search_service.log.es817_20261009_1791478533832080738`、`log/run_off_task.log.es817_20261009_1791478533833602739`。业务代码、工厂、Router及引擎hash和发布候选一致，引擎d9a30277f6464d639a9255800506f8bc9fffeff062834e10cd1839d1df4cd9fc。新引擎正常初始化建立旧端0文档的空默认open_shop；这不是额外迁移客户知识或业务测试写入。

日志在 **120 机器**，不是SG本地；旧文件不会随新进程继续写。新建两个固定软链接，未覆盖已有日志；通过进程stdout文件身份校验确认它们指向实际活动文件，两份日志均非空且随后增长。以下启动命令通过入口追加日志；若另外选择新的时间戳文件，需要同时更新软链接。脱敏证据为同名目录 `current_log_entries.json`。

```bash
tail -f /root/knowledge_database_builder/log/es_search_service.es817.current.log \
        /root/knowledge_database_builder/log/run_off_task.es817.current.log
```

以后手动启动也必须使用该独立环境。以下是原启动参数，执行前确认端口无既有服务，避免重复启动：

```bash
cd /root/knowledge_database_builder
export PATH="$PWD/.venv-es817/bin:$PATH"
export PYTHONPATH="$PWD:${PYTHONPATH:-}"
nohup .venv-es817/bin/python knowledge_database_search_service/src/knowledge_database_search_es.py \
  config/config_for_search_index.json >>log/es_search_service.es817.current.log 2>&1 &
nohup .venv-es817/bin/python control_service/off_task_control_service.py \
  --script-dir /root/knowledge_database_builder --port=6000 >>log/run_off_task.es817.current.log 2>&1 &
```

## 上线后只读验收

在120本机127.0.0.1:8003串行执行六次真实请求，没有新增/修改/删除业务测试数据。search带top_k2/use_synonyms=True，web分页2并限制del_flag0和qa，count显式from_type=chat_auto。

| index / provider | /get_from_type_count | /web_search | /search |
|---|---|---|---|
| mercado_local / Serverless |success true，count387，39.1ms|2结果，169.1ms|2结果，509.2ms|
| payoneer_olive / PaaS |success true，count4939，18.8ms|2结果，60.5ms|2结果，2545.6ms|

均HTTP200、结果ID存在、分数有限；没有仅以HTTP200认定通过。web原total_count字段存在，但本工具汇总取错total名称写成null，故该批不宣称总数逐条验收；原离线契约测试另保留。原输出正文没有保存到公开证据。启动前真实native样本两路均带1024维nested向量，源码仍返回完整source，业务本地重排链和既有插入路径未更换。

当前检索PID1585100另串行完成两次只读get_from_type_count，均success=true：mercado_local393/34.0ms，Olive4970/36.0ms，持久业务写0。比初次请求分别增加6/31，恰好对应这两库本次补入的知识；初次表格保留原观察值，没有覆盖。证据 `current_retrieval_count_readonly.json`。

发布前相关 **300passed、2xfail**；回退保护 **9passed**。两个xfail是原暂缓单条失败状态和未使用es8.17示例别名，不算完整兼容；runtime配置8.17正常。未执行当前集成的业务写压力或全公开接口真实写验收，不将此前test_case native pipeline候选试验冒称为现在已集成。详细实现及未验收范围见 [准备报告](es817_online_release_preparation_20261009.md)。

## 回退

120私有备份 `/root/knowledge_database_builder/backup/es817_release_20261009` 包含原业务/引擎、实际共享legacy引擎、原命令/旧解释器、原git状态和最新精确activation journal。发布后真正执行了回退**只读检查**，返回ready、services_stopped0、3份配置通过；未演练停止/恢复分支。

需要回退时在120执行：

```bash
/root/miniconda3/envs/py38/bin/python \
 /root/knowledge_database_builder/backup/es817_release_20261009/rollback_legacy.py --execute
```

校验备份/活动配置SHA及精确新服务身份，挖掘有任务则保护不停止；优雅停两进程、原子恢复配置、原py38与原参数启动，验证端口，记录进度。不是git reset或ES数据回滚；切换后的新库写入不会反向同步到旧库，回退后需单独对账。这一边界不能称永久新旧双向同步已经部署。

## 数据补差独立进展

固定86原名预检旧202962、新202749净少213，另有3条删除状态不一致；用户已知后明确要求赶紧完成。原migration agent已处理全部340时间候选：新增14次普通更新，其余326个候选已相同。连同先前补缺，累计 **213条CREATE及17条UPDATE，共230次实际ACK且独立完整source/ID/routing读回通过**，失败或目标未知变更0；17条更新的四类向量及nested内容未变。17条中包含旧端恢复为0的joint_login一条及旧端为1的Mercado两条删除标记修正，不是新审核或硬删除。

最终86项身份及del_flag/audit_result/quality_level复核于北京时间01:28:23完成：两端各202962根，完整ID/routing及三个标记索引值逐身份差异0、缺失0、目标额外0、失败0。固定时间窗口内340个不同文档的完整字段均读回通过。先私有完整before/after，create或fresh GET CAS，保护目标并发陌生修改，不重建/改锁/审核/硬删；冲突/陌生目标跳过0。旧端持续可写，这不是永久CDC；时间未变的任意其它正文/字段变化仍未全量source重扫。完整报告 [迁移执行验收](es817_incremental_sync_execution_20261009.md)，逐库CSV/原生身份及标记证据在同名目录；私有完整正文及维护工具继续保留于旧隔离开发现场。

用户随后反馈慢查询，本轮只读排查已确认原ES7 msearch在当前ES8变成逐路串行，尚未修改引擎/配置或重启。新客户端真实msearch保完整source的候选、源SHA及重排分数一致；Serverless40条/路样本512–563ms→348–364ms。PaaS首轮向量took2420ms，热重复18ms，不能把全部差距归因并行。详见 [耗时排查](es817_online_latency_diagnostic_20261009.md)。

脱敏上线证据：同名目录activated.json、health_after.json、readonly_acceptance.json、activation_in_progress.json及manifest.json。120原untracked全部保留；没有干扰SG旧服务、其它检索服务或新项目迁移。
