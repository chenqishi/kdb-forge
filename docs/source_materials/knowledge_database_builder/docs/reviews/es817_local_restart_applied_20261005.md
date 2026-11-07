# 本机旧 8003 服务修复加载与重启验收

2026-10-05。用户要求“那就重启本机服务啊”，随后明确“你重启本机的，为啥跟远端代码有关系”。本机重启和本机修复加载无需远端 commit/push；此前将生产 git pull-only 规定套用于本机操作是错误扩大范围，已纠正。之前提出的远端提交审批不再是本机操作前提，未据此提交/推送。

## 实际完成

- 仅在 `/root/knowledge_database_builder` 应用已验收的 ext_info 两函数修复。先验证旧源 SHA、保存独占备份和精确 diff，先读取本机对应 schema，再 `git apply --check` / `git apply`，最终完整字节与隔离已验收服务一致。
- 本机服务文件 SHA256：`c4f81d69c59159b57072bf10253e2055232cb74224ea4d905c843799511a72db`。
- 仅执行一次 `systemctl restart knowledge-database-search.service`，退出码 0；2026-10-05 **17:35:17 CST** 新 MainPID **3178826**，旧为 1381069。
- 新进程工作目录仍 `/root/knowledge_database_builder/knowledge_database_search_service/src`，旧服务监听 **0.0.0.0:8003**，4 个 worker，active/running。解释器仍现有 `/root/kdb-forge/.venv-es817/bin/python`，不是运行 kdb-forge 应用。
- 未改变当前运行的 ES8 引擎（`caedc4d3269af3a24a8f2f5104e37c60704f8920b11158dc98236f8942abc145`）、工厂、Router、业务消费者、服务/ES 配置、systemd unit、索引名/路由/alias或依赖。隔离引擎 07d08 全部审计改动没有被夹带应用。
- 未重启其它服务/Codex或迁移任务，未 commit/push，未清理/回滚既有现场。生产机器原有上线规范仍适用生产操作。

## 真实 HTTP 验收

`/openapi.json` 200；本服务无 `/health` 路由，不以不存在的 health 接口判断失败。

17:36:27–17:36:42 CST，真实运行旧 8003 HTTP 的 **28 个检查全部通过**（QA 14 + segment 14），退出 0。不是进程内 ASGI 代替运行服务：

- 原 `/insert` 新增成功，native stored source 保存 ext_info 与实际业务扩展字段；id/index/refresh/LLM/update 等控制字段未自动混入。
- 原 `/search`、`/web_search` 能回读 ID、正文与完整 metadata。
- 原 `/insert` content-only 局部更新保留未指定 metadata、正文以外信息及各类向量。
- ext_info-only partial patch 合并新键，原文件来源、扩展字段、正文及 root/nested 向量保留。
- 原 `/delete` 删除成功、native GET 404；重复删除返回旧 False；HTTP 再查询为空、total/current 为 0。

只使用此前已授权准确自有 A 名 `codex_source_probe_20261004_63a68e52aebb_a`、固定 `source-probe`、默认 routing；建前404、完整 source、owner/UUID/无 alias/单 ID 保护，QA/segment顺序复用前确认删除。阶段清理 GET 404；17:38:20 两个 provider 的 A/B 四个准确索引 GET 再次全部 404。没有真实业务/旧 ES7/staging 写或审核/删除客户知识，Script/条件更新/按文件软删继续按用户要求暂缓。

本次运行 HTTP 合成 CRUD 写入目标为 Serverless；PaaS 的真实隔离 82 检查是原报告历史，本次不冒称运行 HTTP 在 PaaS 完整写验收。另做两端原物理名的限量真实 HTTP 只读检查：

| 原索引 | provider | `/web_search` | `/search` 固定既存样本 | 分数 |
|---|---|---|---|---:|
| mercado | Serverless | 200，1条，ID存在，无error | 200，1条，目标ID命中 | 1.165704894952807 |
| payoneer | PaaS | 200，1条，ID存在，无error | 200，1条，目标ID命中 | 1.1745921811174533 |

真实 `/search` 使用已有样本标题生成少量 query embedding，报告仅记录长度、ID hash、分数，不保存业务原文/向量/凭据。两个固定样本通过不能当全 query 质量、并发或永久同步验收；未计精确全库 total。

## 命令与证据

本机修复：`es817_local_restart_applied_20261005/service_only.diff`；原代码备份 `service_before.py.txt`；先后 unit/config/源码哈希 `before.json`、`after_ready.json`、`final_check.json`。

真实运行 HTTP：

```bash
env -C /root/knowledge_database_builder-es8-dev \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/root/knowledge_database_builder-es8-dev:/root/knowledge_database_builder-es8-dev/tests \
  /root/kdb-forge/.venv-es817/bin/python tests/es8_crud_acceptance_20261005.py \
  --execute --phase running_old_HTTP \
  --output /root/knowledge_database_builder/docs/reviews/es817_local_restart_applied_20261005/live_running_HTTP.json
```

工具来自隔离旧项目，接口请求实际发送到已重启的本机 `127.0.0.1:8003`；工具的 fixture/只读 client 不替换运行服务的真实 ES 客户端。证据同时记录 dev 和运行 service c4f81、dev engine07d08/运行enginecaed 两种基线，不能混同。

live JSON 的 `service_restart_deploy_commit_push=false` 表示验收工具自身没有执行重启/提交；本机应用与实际一次重启在独立 before/after unit 证据中明确记录。保留原始结果，不覆盖历史。

独立最终核验：28 passed、0 failed；原两索引 HTTP 查询各通过；四个 probe GET 均404；engine/factory/Router/business/config/unit 七个基线哈希全部未变，PID仍3178826，无重复重启。root `git diff --check` 通过。

此前修复已通过新12+旧50=62回归、隔离两端82真实检查；本轮28是真实运行服务复验，不把历史用例重复加成一份更大的测试数字。发布准备时回归 fixture 已改为自足，并分别在运行 enginecaed 与隔离 engine07组合各12通过，详见旧隔离报告的 release XML；本轮没有再改服务实现。

## 留存与边界

当前本机 main 保持原 HEAD a36efc7245dedf2492f5be396f87390885f3a4f4，加用户授权的本地服务修改和本机函数 schema；所有原未跟踪配置、数据、输出、临时脚本和 MEMORY 脏改动保留。未来拉取远端时需保护此已应用补丁，不能 reset/覆盖。

本机 ext_info 修复已经生效；历史入库缺 metadata 没有凭空补数据。其余 ES8 审核/兼容限制、Script、质量压力/持续同步仍沿用原任务边界。本轮不宣称所有任务关闭。

MEMORY 在本机与隔离目录均追加实际结果和纠正：本机操作不自动要求远端提交；只有实际生产发布才应用生产 git pull 规则，不能把“重启本机”误扩为远端 commit/push。按用户已有要求通知既有 wholeagent：旧8003当前服务修复已加载，可继续测试。
