# 来源统计接口本机加载与重启验证，2026-10-08

用户在旧、新隔离实现交付后明确要求“重启本机的”。按此前本机加载流程，先核验当前源代码、保存备份、应用已验收功能增量并复跑测试，然后仅重启对应检索服务。实际生产机器的 git pull 规则仍适用于生产发布；此次没有远端发布或 commit/push。

| 项目 | 实际本机工作目录 | 服务 / HTTP | 重启后的 PID | 本机回归 |
|---|---|---|---:|---:|
| 旧 | /root/knowledge_database_builder | knowledge-database-search.service / 8003 | 3751589，08:59:00 CST | 218 passed，6.20s |
| 新，指定 sg-kg 既有会话执行 | /root/kdb-forge | kdb-forge-retrieval.service / 127.0.0.1:8012 | 3751674，08:59:30 CST | 322 passed，2.419s |

旧服务原 PID 3214210，新服务原 PID 2802557。两个 unit 均 active/running、NRestarts=0，分别执行一次有授权的 restart；没有重启 Codex、迁移或其他服务。旧服务仍运行旧目录实现，使用现有 ES8.17 解释器路径不表示改用新版业务代码。未更换依赖或虚拟环境。

## 已实际加载

两版 POST /get_from_type_count 均已出现在运行服务 OpenAPI；from_type 默认 chat_auto，固定 quality_level=high，两个时间齐全才追加 insert_time 含端点范围。原物理索引名原样使用，不做公私库扩展或版本名转换，不追加审核/软删除/类目条件。计数使用原生 _count，计数路径不创建缺失索引。

旧目录应用的37个功能文件与已验收隔离实现逐 SHA 相符；五个实现文件与真实只读测试所执行版本一致。先 git apply --check、保存原文件与 git 状态，再应用功能 diff。原有 ext_info/自动建库修改完整保留，没有夹带 es8-dev 的广泛审计改动。另复用既有 metadata 回归文件及 schema，未覆盖既有文件。

新版应用的是其指定会话产出的任务增量 patch；26个功能文件与隔离 manifest 完全相符，原有脏改动保留。两个项目的 unit、运行配置、provider/路由、索引/alias 均未修改。没有 reset/clean/stash、提交/推送、真实 ES 持久写或干扰独立迁移。

## 真实运行 HTTP 结果

旧8003：12个统计接口/native计数配对全部一致，覆盖两provider默认/显式chat_auto、document、无命中来源、双边时间与单边时间；6个空索引及错误参数控制全通过；mercado_local、payoneer_olive 的原 /search 与 /web_search 各一次，四次均正常返回非空ID。运行API实际使用原HTTP请求，没有用ASGI代替上线验证。

新8012：4个真实接口/native配对一致，覆盖两provider默认来源和双边时间；9个认证/参数/空名控制全通过；health 200，既有路由保留。错误Basic、带代理头而无Basic、无效Bearer均401，没有放宽认证。此次新版运行HTTP统计共13个案例，隔离阶段12配对仍是此前验证，不混计成重启后全部复跑。

| 原索引 | 默认 chat_auto，旧8003/新8012 | 2026-09-01 至 2026-10-08，旧8003/新8012 |
|---|---:|---:|
| mercado_local，Serverless | 387 / 387 | 50 / 50 |
| payoneer_olive，PaaS | 4939 / 4939 | 2378 / 2378 |

这里“旧8003”指旧项目的本机 ES8.17 服务，不是源端ES7。源端Local计数388/51，新端387/50的一条同步差额仍未补写；重启不会追平数据。原检索排序、空类目数组语义、web total下界等已记录问题没有因为新接口加载而关闭。原检索的四个smoke不构成全量召回/重排或CRUD写验收；本轮不执行 insert/delete 或条件更新。

## 命令与可复核证据

旧重启命令：`systemctl restart knowledge-database-search.service`；新重启命令由指定会话执行：`systemctl restart kdb-forge-retrieval.service`。

旧运行HTTP复核工具：

```bash
env -C /root/knowledge_database_builder \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/root/knowledge_database_builder:/root/knowledge_database_builder/tests \
  /root/kdb-forge/.venv-es817/bin/python tests/from_type_count_live_20261008.py
```

工具拒绝覆盖既有证据；复跑须先为新一轮证据指定新位置，不能删除旧结果。仅已有两个索引HEAD、12个native_count、真实localhost接口与两次既有search向量生成，无业务或staging写测试。

- 旧备份、源代码状态与unit前后证据：[before.json](/root/knowledge_database_builder/docs/reviews/from_type_count_local_activation_20261008/before.json)、[after.json](/root/knowledge_database_builder/docs/reviews/from_type_count_local_activation_20261008/after.json)；同目录 backup 保留原文件，applied_feature.diff 为功能增量。
- 旧运行HTTP：[live_running_http.json](/root/knowledge_database_builder/docs/reviews/from_type_count_local_activation_20261008/live_running_http.json)；实际218回归日志为同目录 local_regression.log。
- 新准备及备份指针：[learning_count_restart_prepare_20261008.json](/root/kdb-forge/artifacts/learning_count_restart_prepare_20261008.json)。
- 新运行HTTP：[learning_count_restart_live_20261008.json](/root/kdb-forge/artifacts/learning_count_restart_live_20261008.json)；322本机回归XML为同目录 learning_count_restart_offline_regression_20261008.xml。
- 开发阶段完整diff、方法契约、SHA及类目结果见[原综合验收报告](/root/knowledge_database_builder/docs/reviews/from_type_count_old_new_acceptance_20261008.md)。其“未加载”说明记录的是此次明确重启授权之前的历史状态，以本报告为当前运行状态。
