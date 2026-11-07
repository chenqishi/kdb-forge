# 聊天 QA 自动学习生产任务 PRD v20260613-Payoneer

## 项目背景

knowledge_database_builder 的聊天 QA mining 用于从客户群聊中沉淀可复用业务知识，并写入对应客户的 ES 知识库，供前端审核、自动学习统计和后续召回使用。

生产链路必须满足三件事：

- 客户严格隔离：A 客户聊天只能进入 A 客户索引，不能 fallback 到默认客户或其它客户。
- 新客户可自动学习：新纳入的 app 第一次运行时要有足够回溯窗口，不能因为没有 app 游标而只扫最近一次全局定时窗口。
- 运维可观测：每天 09:00 的学习日报必须能稳定产出，即使旧消息转发通道不可用，也不能让定时任务误报失败。

## 当前生产流程

定时任务在 120 上通过 crontab 执行：

- `00 12,18 * * * /root/knowledge_database_builder/control_script/timing_run_task_gen_knowledge_by_send_request.sh`
- `00 09 * * * /root/knowledge_database_builder/control_script/timing_run_chatqa_learning_report.sh`

聊天 QA 主任务流程：

1. `batch_run_chatqa_request.py` 从 `rf_ai_role_config` 查询 `timing_run_chat_mining=1` 的 app。
2. 联表 `rf_app_info` 获取 `customer` 作为 `client`、`application_name` 作为 `user`。
3. `client/user` 为空直接跳过，禁止 fallback。
4. 对每个 app 调用本机 `off_task_control_service` 的 `/start_task` 创建 `chat_qa_mining` 任务。
5. `ChatQAMiningTaskController` 按数据提取、QA 生成、质量分桶、schema 转换、ES 写入执行。
6. 数据提取 SQL 强制按 `customer + app_id + 时间窗口 + del_flag` 限定。
7. ES 写入前校验 `platform/client/ext_info.client` 必须与当前任务 `client` 一致。
8. 审核回流接口更新 `audit_result` 时要求 `client == index_name`。

## 本次热修结论

### 0. Payoneer 相关 app 纳入自动 QA mining

Payoneer 缺失原因：

- 生产库里除已开启的 `individual_20_Payoneer_0_we_com` 外，还有多个 `payoneer/Payoneer` 命名的有效 app。
- 这些 app 本身 `rf_app_info.is_enabled=1`、`del_flag=0`，但缺少 `timing_run_chat_mining=1`，所以定时入口不会自动拉起 QA mining。
- 部分 app 当前聊天量很少或为空，但客户、应用、索引归属明确，启用后不会跨客户 fallback；没有数据时只会产出空任务结果。

本次处理：

- 保持已有配置：
  - `2031630102065340418 / individual_20 / individual_20_Payoneer_0_we_com / config_id=655`
- 新增启用配置：
  - `2031631929972383745 / individual_20 / Payoneer_individual_20_demo_cm / config_id=873`
  - `2058771265889034242 / individual_20 / individual_20_Payoneer_Chloe_MarsMind_1_we_com / config_id=874`
  - `2058811579274158081 / individual_22 / Payoneer123_individual_22_demo_cm / config_id=875`
  - `2059149594118905858 / payoneer / payoneer_payoneer_demo_cm / config_id=876`
  - `2062769895700504578 / payoneer / payoneer_payoneer_1_we_com / config_id=877`

未启用项：

- `2057405844619264002 / payoneer_scrm_activate`：`rf_app_info.is_enabled=0` 且 `del_flag=1`。
- `2057426462639128578 / payoneer_scrm_activate2`：`rf_app_info.is_enabled=0`。

这些 app 虽然名称包含 Payoneer，但应用本身处于停用或删除状态，本次不绕过 `rf_app_info.is_enabled=1` 规则。

### 1. Wayfair 纳入自动 QA mining

Wayfair 缺失原因：

- `wayfair` 存在启用 app：`2019449490957221890 / wayfair_wayfair_test2_1_we_com`。
- 该 app 缺少 `timing_run_chat_mining=1`，所以批量入口没有拉起任务。
- 另一个 `2058790521796091906 / wayfair_weijuhui` 虽然最近聊天量较多，但 `rf_app_info.is_enabled=0`，本次不直接启用，避免误影响线上助手行为。

本次处理：

- 对启用 app `2019449490957221890` 插入 `rf_ai_role_config.id=872`：
  - `config_key=timing_run_chat_mining`
  - `config_value=1`
  - `config_type=BOOLEAN`
  - `client=wayfair`
  - `is_enabled=1`
  - `del_flag=0`

验证后当前可运行 app 从 5 个变为 6 个，新增：

- `client=wayfair`
- `user=wayfair_wayfair_test2_1_we_com`
- `app_id=2019449490957221890`

### 2. 新 app 第一次运行回溯修复

旧逻辑：

- 如果 app 不在 `data/chatknowledge/appid_record.txt`，默认开始时间会使用全局 `run_timing_record` 的上次运行时间。
- 新纳入 Wayfair 后，下一次定时任务可能只从当天中午开始扫，错过之前一个月的历史聊天。

新逻辑：

- 只有没有 app 级游标的新 app，默认从当前时间往前 30 天开始。
- 已有 app 仍使用自己的 `appid_record` 增量游标，不改变既有增量行为。

验证：

Wayfair 新任务请求会构造为：

```text
client=wayfair
user=wayfair_wayfair_test2_1_we_com
index=wayfair
app_id=2019449490957221890
start_time=2026-05-14 17:08:46
end_time=2026-06-13 18:00:00
```

### 3. QA search data 写入 task_id

旧问题：

- schema 转换命令使用 `--task_id`，在 Python Fire 下未稳定映射到函数参数，导致输出 search data 的 `task_id` 为空。
- 这不影响客户隔离，但影响按任务追溯 ES 写入结果。

新逻辑：

- `ChatQAMiningTaskController.stage_4_schema_transform()` 改用 `--task-id={task_id}`。
- 转换小样已验证输出顶层 `task_id=taskid_smoke_20260613`。

### 4. 日报任务不再因发送失败阻断

旧问题：

- 09:00 学习日报会调用旧 HTTP 转发地址，如 `http://120.77.147.247:9900/send`、`9905/send`。
- 当前地址 connection refused，脚本抛出异常，导致 cron 日志显示失败。

新逻辑：

- 日报始终先生成文本并写入 `log/chatqa_learning_daily_report_latest.txt`。
- 发送失败只记录错误，不中断定时任务。
- 如需严格发送失败即失败，可手动加 `--strict-send`。

验证：

- 使用不可用地址 `http://127.0.0.1:9/send` 做发送失败测试，进程退出码为 `0`。
- 日报文本正常写入 `log/chatqa_learning_daily_report_smoke.txt`。

### 5. 旧审核报表补齐 client

旧问题：

- `batch_gen_audit_data_and_send.py` 从 ES 导出审核报表时，部分历史 ES 行只有 `platform`，`client` 为空，容易被误解为无客户归属。

新逻辑：

- 导出 `audit_data_{flag}.txt` 后执行归属补齐：
  - 若 `client` 为空且 `platform` 存在，则 `client=platform`。
  - 若 `ext_info.client` 为空，也同步补齐。

验证：

- 小样 `platform=wayfair/client为空/ext_info为空` 处理后变为 `client=wayfair/ext_info.client=wayfair`。

## 客户隔离规则

生产链路必须继续遵守：

- 缺 `client` 或缺 `user` 的 app 直接跳过。
- SQL 抽数必须限定 `customer=%s AND app_id=%s`。
- ES 目标索引默认使用当前任务 `client`。
- 写 ES 前必须校验输出行的 `platform/client/ext_info.client`。
- 人工审核更新 `audit_result` 时必须校验 `client == index_name`。
- 不允许把空客户 fallback 到 `default_client`。
- 不允许把个人池、共享池、离线导入池混写，除非任务显式声明并经过校验。

## 验收结果

- 120 生产代码语法检查通过：
  - `control_script/batch_run_chatqa_request.py`
  - `control_script/chatqa_learning_daily_report.py`
  - `control_script/batch_gen_audit_data_and_send.py`
  - `control_service/chat_qa_mining_task_control.py`
  - `commons/schema_trans.py`
- 当前启用 app 列表已包含 Wayfair，合计 6 个可运行 app。
- Payoneer 配置补齐后，当前可运行 app 合计 11 个。
- Payoneer 任务请求验证通过：
  - `individual_20_Payoneer_0_we_com` 使用既有 app 游标，从 `2026-06-13 12:00:01` 增量运行。
  - 新增 Payoneer app 使用新 app 默认回溯，从 `2026-05-14 17:15:28` 开始回扫 30 天。
  - `individual_20` 相关 app 写入 `index=individual_20`。
  - `individual_22` 相关 app 写入 `index=individual_22`。
  - `payoneer` 相关 app 写入 `index=payoneer`。
- 缺 client 的两个历史 app 仍被跳过。
- `task_id` 转换小样通过。
- 日报 dry-run 通过。
- 日报发送失败不阻断小样通过。
- 旧审核导出 client 补齐小样通过。

## 备份

120 代码备份：

- `backup/chatqa_learning_daily_report.py.bak_daily_wayfair_20260613_170647`
- `backup/batch_gen_audit_data_and_send.py.bak_daily_wayfair_20260613_170647`
- `backup/chat_qa_mining_task_control.py.bak_daily_wayfair_20260613_170647`
- `backup/batch_run_chatqa_request.py.bak_new_app_backfill_20260613_170844`

120 数据库配置备份：

- `backup/wayfair_timing_config_before_20260613_170647.json`
- `backup/payoneer_timing_config_before_20260613_171510.json`

## 后续建议

- 如果确认 `2058790521796091906 / wayfair_weijuhui` 虽然 app 禁用但仍应参与 QA mining，建议新增 QA-only 白名单机制，而不是直接取消 `rf_app_info.is_enabled=1` 过滤。
- 如果确认已停用的 `payoneer_scrm_activate2` 仍要参与 QA mining，建议先明确它是否只是助手停用、但聊天数据仍需要学习；不要直接把停用 app 纳入自动任务，避免对线上助手生命周期语义造成混乱。
- 如果 09:00 日报必须真实推送飞书，需要在 120 配置飞书机器人 webhook 或飞书应用凭证，并把日报脚本从旧 wx 转发切换到飞书 API。
