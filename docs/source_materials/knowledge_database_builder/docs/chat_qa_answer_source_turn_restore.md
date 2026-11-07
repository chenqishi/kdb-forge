# Chat QA answer-source Turn 恢复说明

## 目的

把 2026-07-27 前在生产运行、但未提交到 Git 的 answer-source Turn 链路恢复到可评审、可测试、可发布的正式分支。

恢复分支基线：

- 当前 `main`: `de7810689dad7a30d3739be96f76d987ce93259a`
- 历史生产快照: `a09e4df66d97da812176d22c4c63898659ff0a1c`
- 身份优先级修复参考: `stash@{2026-06-25 19:34:44 +0800}` / `bak_answer_source_priority_20260623_011128`

## 恢复范围

只恢复聊天 QA 主链路，不带入历史 stash 中同时存在的文档 QA、HTML 清洗和架构文档改动：

- `chatknowledge/gen_knowledge_from_chat.py`
- `control_service/chat_qa_mining_task_control.py`
- `control_script/batch_run_chatqa_request.py`
- `control_script/timing_run_task_gen_knowledge_by_send_request.sh`

保留当前 main 的 `commons/schema_trans.py`、搜索接口、ES 接口和 `chat_qa_extract/` 文件，避免下游 Schema/搜索能力倒退。恢复后的聊天 QA 主路径不再调用 `chat_qa_extract`，而是按 answer-source Turn 直接请求 JSON LLM。

## 核心行为

1. 用通讯录、群白名单和 app Prompt 同事名单识别答案来源人。
2. 显式白名单/同事名单优先于通讯录默认身份。
3. 只围绕 leader/同事候选答案构建 answer turn。
4. 同一发送者 180 秒内连续候选答案可合并；客户或非答案消息会关闭当前 turn。
5. 每个 turn 最多取前 50 条同群消息作为问题上下文。
6. 模型只能从 `【当前待评估答案】` 生成答案；程序继续校验来源人和文本重叠。
7. 模型直接返回 `quality_level`，controller 只做 high/mid/low 兼容分桶，不再调用第二个质量模型。
8. Schema 继续携带 `task_id`；ES 写入前继续校验 client/platform 归属。

## 同步保留的生产安全规则

- 缺少 `client` 或 `user` 的 app 直接跳过，禁止 fallback 到默认客户。
- `chat_mining_scene_type` 只接受 `group`、`single`、`group,single`，非法值回退到 `group`。
- 只有最终完成的 app 才推进 app 水位；启动失败或运行失败保留旧水位。
- 任一外层定时步骤失败时，全局水位不推进。
- 单个群处理失败时继续收集其它群的失败证据，但整项 App 任务最终按失败结束，不写 ES、不推进 App/全局水位。
- 直连模型凭据缺失或请求重试耗尽时抛出硬失败，不再把空结果当作成功。
- 启用 App 查询为空时批任务硬失败，避免数据库/配置异常被误判为“无任务正常结束”。

## 可观测性与超时

- 每项任务写入 `data/off_task_data/<task_id>/llm_call_stats.json`，记录逻辑调用、HTTP 尝试、成功/失败/超时次数、字符数、模型返回的 token usage、耗时和群处理结果；汇总同时进入任务结果 `llm_call_stats`。
- `CHAT_QA_TASK_TIMEOUT_SECONDS`：单项 App 任务总时限，默认 21600 秒；超时会终止当前阶段进程组并将任务置为失败。
- `CHAT_QA_POLL_TIMEOUT_SECONDS`：批量调度等待所有 App 任务的总时限，默认 21600 秒；超时任务按失败处理。
- `CHAT_QA_STATUS_REQUEST_TIMEOUT_SECONDS`：单次状态查询 HTTP 超时，默认 10 秒。
- `CHAT_QA_POLL_INTERVAL_SECONDS`：状态轮询间隔，默认 10 秒。

## 验证

```bash
python -m py_compile \
  chatknowledge/gen_knowledge_from_chat.py \
  control_service/chat_qa_mining_task_control.py \
  control_script/batch_run_chatqa_request.py

bash -n control_script/timing_run_task_gen_knowledge_by_send_request.sh

pytest -q tests
```

正式 `tests/` 全集 98 项通过；Python 编译、Shell 语法和 `git diff --check` 通过。仓库根目录直接执行裸 `pytest` 会额外收集 `knowledge_crawler_tool/tmp/test_chromdriver.py`，审计环境未安装 Selenium；该历史临时脚本不属于本次变更。

## 发布边界

本分支只完成代码恢复和离线验证，不修改生产 crontab、不启动真实批任务、不调用生产 LLM/数据库/ES。当前可检查的上线参考目录 `/root/knowledge_database_builder` 未发现 `config/chatknowledge_llm_env.sh`，当前进程环境也未发现支持的模型变量；发布负责人必须在启动服务和定时任务的真实生产运行环境中确认凭据已安全注入，且不得把密钥提交到 Git。正式上线需走 QA/发布门禁，先用一个 App 做最小影子/灰度验证，再放开定时任务。

## 应用状态与抽取状态解耦

- `rf_app_info.is_enabled` 继续表示线上应用是否启用，不应为了运行知识抽取而修改。
- `timing_run_chat_mining=1` 表示账号允许进入每日聊天 QA 抽取。
- 默认情况下，停用应用仍不会进入定时任务。
- 只有账号显式配置 `chat_mining_allow_disabled_app=1` 时，才允许在
  `rf_app_info.is_enabled=0` 的情况下继续执行知识抽取。
- 该例外配置必须按账号设置，不能作为全局默认，避免历史停用账号被意外重新纳入。
