# 聊天 QA 自动学习 PRD v20260904-v17

## 1. 产品目标

knowledge_database_builder 从客户群聊中沉淀可复用业务知识，写入当前客户的 ES 知识库。系统必须同时满足：

- 只把真实人类同事的回复作为答案来源。
- 一条知识的答案只能来自当前 answer-source Turn。
- 候选抽取与入库质量审核使用独立模型请求。
- 只有审核为 `accept + high` 的知识才可自动入库。
- 临时、个案、敏感、错误脱敏和 AI 回复不得进入长期知识库。
- 客户、应用、索引和 category 必须严格隔离并可追溯。
- 任务结果中的 `qa_num` 必须代表真实成功入库数。

## 2. 范围

本版本影响 `chat_qa_mining` 任务，包含定时批处理和未来 webhook 触发的单 Turn 处理。

不改变：

- app 的在线、停用、删除和回复能力状态。
- 文档、HTML、Excel 的 QA/segment 导入流程。
- 存量 ES 知识的审核状态。

## 3. 生产现状与根因

2026-09-04 生产核对结果：

- Answer-Turn 抽取已以“同事回复为锚点、同人 180 秒内合并、向前 50 句上下文、答案只来自当前 Turn”运行。
- 当前阶段 3 只把第一个模型的 `quality_level` 重新分桶，没有第二次质量模型请求。
- schema 转换会传递 high/mid/low，原入库器没有质量准入闸门。
- 任务 `qa_num` 只统计入库前 high 候选，不是真实入库量。
- 今日 18:00 批次为 high 101 + mid 80 = 181 条待写，查重跳过 26，实际写入 155，所以旧 `qa_num=101` 与最终入库量不一致。
- `payoneer_olive` 的生产 category 树以平台名为一级类目，包含 Bol、Chewy、Wayfair、TikTok Shop 等。当前聊天抽取能识别 `model_platform`，但转换时丢失，最终全部进入默认分组。

## 4. 输入契约

`chat_qa_mining.task_info` 必填：

- `client`
- `user`
- `app_id`
- `start_time`
- `end_time`

可选：

- `index/index_name`
- `scene_type`
- `category_name/categoryName`
- `category_id/categoryId`
- `category`：可为平台名字符串，或包含 categoryName/categoryId 的 object

候选 QA 可额外带：

- `category_infos`
- `marketplace/model_platform`
- `source_message_ids/source_user_id/source_identity`
- 其它 webhook 追溯字段

审核阶段必须保留所有上游字段，不得因模型输出 schema 而删除 category 或追溯信息。

## 5. 身份与 Answer Turn

### 5.1 身份角色

- `leader/可作为答案来源`
- `同事/可作为答案来源`
- `客户/只能作为问题来源`
- `未识别/不能作为答案来源`

通讯录中明确设置为静默/不可作为答案源的账号拥有 veto 权，必须覆盖 system prompt 中的过期同事名单。这一配置只影响知识学习，不改变 app 线上状态。

### 5.2 Turn 规则

- 以可作为答案来源的消息为锚点。
- 同一稳定发送人 ID 在 180 秒内连续回复可合并。
- 客户插话、换人或超时结束当前 Turn。
- 向前最多携带 50 句作为问题上下文。
- 答案不得使用上下文中其它回复。

## 6. 两阶段模型管道

### 6.1 阶段 A：候选抽取

输入为当前 Turn + 向前 50 句；输出 q/a、source_quote、source 身份、平台、抽取器质量判断和追溯 ID。

抽取器的 high/mid/low 仅是候选信号，不能直接决定入库。

### 6.2 程序硬过滤

第二模型之前先拒绝高确定性风险：

- AI 助理/机器人答案源。
- 明确非人工答案身份。
- 损坏核心业务对象的脱敏占位符。
- 未脱敏邮箱、手机号、超长可定位编号。

硬拒绝项不消耗第二次模型请求。

### 6.3 阶段 B：独立审核

只审核阶段 A 产生的候选，不审核空 Turn。审核模型看到：

- 原始 q/a（只读）
- source_quote
- 当前 Turn 与必要上下文
- source 身份
- client 和 model_platform

输出：

- `decision=accept|review|reject`
- `quality_level=high|mid|low`
- `grounded`
- `knowledge_scope`
- `sensitive`
- `temporary/valid_until`
- `reason_codes/reason`

审核模型不修改 q/a。模型返回无法解析或请求失败时，默认 `review + mid`，禁止自动入库。

## 7. 入库准入

自动入库的必要条件：

```text
review_decision == accept
AND quality_level == high
AND grounded == true
AND sensitive == false
AND temporary == false
AND knowledge_scope != client_specific
```

条件不满足时不调用 embedding/查重/ES 写入。`review` 保留在任务产物中供后续人工处理，`reject` 仅保留追溯记录。

实际写入前依然执行现有标题查重和 client/index 归属校验。

## 8. Category 兼容

优先级：

1. 候选上游已携带的 `category_infos`。
2. QA/webhook 携带的 category_name/category_id/category object。
3. task_info 携带的 category_name/category_id/category object。
4. 对 `payoneer_olive`，使用 `marketplace/model_platform` 作为 category_name 候选。
5. 若模型平台字段为 unknown/租户名或未命中，则仅对 `payoneer_olive` 在实时类目树内，用候选标签和问题原文精确匹配平台名；短英文平台名必须满足词边界。
6. 在当前 client 类目树中解析 category_name 并补 category_id/primary_category；无效的模型候选不得覆盖后续有效候选。
7. 无法解析时才使用“默认分组”。

`platform/client/dataset` 始终保持客户值 `payoneer_olive`；Bol/Chewy/Wayfair 等平台名写入 category，不得覆盖客户归属。

## 9. 统计契约

任务结果必须返回：

- `extracted_candidate_num`
- `high_candidate_num/mid_candidate_num/low_candidate_num`
- `review_accept_num/review_pending_num/review_reject_num`
- `insert_attempt_num`
- `duplicate_skip_num`
- `gate_skip_num`
- `insert_failure_num`
- `insert_success_num`
- `qa_num`：与 `insert_success_num` 相同，为真实成功入库量
- 抽取和审核两阶段的 token/调用统计

`metrics_complete=false` 表示没有拿到入库器结果文件，不得用候选数猜测入库数。

## 10. 失败和幂等

- 抽取失败：当前组任务失败，不推进 watermark。
- 审核单条失败：该条进 review，不入库，其它条继续。
- schema/client 校验失败：阻断整个写入阶段。
- ES 写入异常：写入当前统计文件后任务失败。
- 查重命中：记录 duplicate_skip，不计入 qa_num。
- 未来 webhook 使用 `client + app_id + source_message_ids` 构造幂等键。

## 11. 验收标准

- 被标记为静默的 AI 账号即使仍出现在历史 prompt 同事名单中，也不生成 Answer Turn。
- 明显 AI 助理名称的存量候选不调用审核模型，直接拒绝。
- mid/low/review/reject 都不调用 ES 写入。
- 审核模型不得修改 q/a 和上游扩展字段。
- Payoneer Olive 显式传入 `Bol + category_id` 时原样保留。
- Payoneer Olive 只有 `model_platform=Bol` 时，能映射到生产 Bol category_id。
- Payoneer Olive 的 `model_platform` 错填租户名、但标签/问题明确出现 Chewy 时，能从实时类目树映射到 Chewy；不得把平台名单写死在代码中。
- `qa_num == insert_success_num`，查重和闸门跳过可单独对账。
- 其它入库调用方不传闸门参数时保持旧行为。

## 12. 发布和回滚

发布前：

- 运行语法检查和相关单测。
- 在生产依赖环境运行离线小样，验证审核、闸门、统计和 category 映射。
- 不在 12:00/18:00 批任务运行中切换代码。

回滚：

- 回退本版本代码并重启 `off_task_control_service`。
- 本版本不修改存量知识，回滚无需 ES 数据迁移。
