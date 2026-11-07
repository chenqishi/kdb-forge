# audit_from_type_count_readonly.py

任务：`LEARNING-COUNT-API-20261008`。离线计划／受限只读验收，不部署接口。

## 输入

`--execute` 可选（默认离线）；`--config` 指向新检索 runtime；`--target-config` 指向已确认的新 ES8 端点配置；`--start/--end` 为本地日期字符串；`--report` 为脱敏 JSON 输出。

## 行为与输出

- `main`：默认只打印计划，不导入业务组件、不联网、不写报告；执行模式输出验收 JSON 和退出码（成功 0，失败 1）。
- `execute`：真实 `KnowledgeService.from_count_config`、Repository、Engine、官方 ES client；进程内 `TestClient` 请求尚未部署的 API。只允许 `mercado_local`／Serverless 和 `payoneer_olive`／PaaS 的原生 `_count`，最多 24 次请求；所有其他 ES 路径及 embedding 构建／ensure 都以拦截器拒绝。
- `cases/native_query`：独立原生查询仅包含 `quality_level=high`、精确 `from_type`，双时间为闭区间。覆盖默认、完整时间／camel alias、其他类型、未知合法类型、有效单边、倒序时间；空／缺／null 索引检查不初始化 service、不请求 ES。
- `require/AuditFailure`：仅将自定义脱敏原因输出；不记录客户端异常原文。`utc_now/read_json/digest` 为本地时间、JSON 与 SHA 辅助。
- 验收报告包含 provider、索引、原生/API 数量、通过状态、端点 hash 和请求路径，不包含正文、向量或认证。

## 限制

不查询旧 ES，不创建索引、不写 ES，不开启监听端口、不重启服务，不证明已部署的 8012 端点可用或数据已同步。环境及 auth 只在本进程临时覆盖，执行完成后恢复；只有本次创建的客户端会被关闭。
