# 聊天 QA 自动学习 PRD v20260904-v18

## 1. 产品目标

knowledge_database_builder 从客户群聊中沉淀可复用业务知识，写入当前客户的 ES 知识库。系统必须同时满足：

- 只把真实人类同事的回复作为答案来源。
- 一条知识的答案只能来自当前 answer-source Turn。
- 候选抽取与入库质量审核使用独立模型请求。
- 只有审核为 `accept + high` 的知识才可自动入库。
- 临时、个案、敏感、错误脱敏和 AI 回复不得进入长期知识库。
- 保留历史生产聊天 QA 已有的来源、证据、时间、标签和图片补充字段。
- 不把任意新字段写入 ES，避免 mapping 膨胀和字段类型冲突。
- 客户、应用、索引和 category 必须严格隔离并可追溯。
- 任务结果中的 `qa_num` 必须代表真实成功入库数。

## 2. 范围

本版本影响 `chat_qa_mining` 任务，包含定时批处理和未来 webhook 触发的单 Turn 处理。

不改变：

- app 的在线、停用、删除和回复能力状态。
- 文档、HTML、Excel 的 QA/segment 导入流程。
- 存量 ES 知识的审核状态和字段值。
- 现有 ES 字段名称与字段语义。
- 未进入历史聊天 QA 字段契约的任意 `info/reference_knowledge/evidence` 字段。

## 3. 生产现状与根因

2026-09-04 生产核对结果：

- Answer-Turn 抽取以“同事回复为锚点、同人 180 秒内合并、向前 50 句上下文、答案只来自当前 Turn”运行。
- v17 已增加独立审核模型、程序入库闸门、真实入库统计和 Payoneer Olive category 映射。
- v17 审核阶段通过复制候选对象保留所有字段，但 schema 转换阶段重新构建 `ext_info`，只复制部分白名单。
- 2026-06 的生产任务曾保留 `source/source_quote/candidate_answer_time/quality_reason/supplement` 等字段。
- 2026-09-04 最近任务的 schema 产物仅保留 `from_chat_history/from_file_name/from_page/quality_info`，说明旧字段兼容曾回退。
- 任意透传未知字段会产生 ES mapping 膨胀和同名字段类型冲突，不能用无约束 merge 修复。

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
- `category`：平台名字符串，或包含 categoryName/categoryId 的 object

候选 QA 可带：

- q/a 与质量字段
- 来源、证据、回答时间和原群聊上下文
- 平台和 category 字段
- 图片 supplement
- 审核、身份和消息追溯字段

已知字段既可以位于候选顶层，也可以位于候选已有的 `ext_info`；顶层值优先。

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

第二模型之前拒绝高确定性风险：

- AI 助理/机器人答案源。
- 明确非人工答案身份。
- 损坏核心业务对象的脱敏占位符。
- 未脱敏邮箱、手机号、超长可定位编号。

硬拒绝项不消耗第二次模型请求。

### 6.3 阶段 B：独立审核

审核模型只判定，不修改 q/a。输出 `decision/quality_level/grounded/knowledge_scope/sensitive/temporary/valid_until/reason_codes/reason`。

模型返回无法解析或请求失败时，默认 `review + mid`，禁止自动入库。审核过程复制完整候选后追加审核字段。

## 7. ES 字段契约

### 7.1 顶层字段

保留：

- `title/content/synonyms_title/data_type`
- `platform/client/dataset`
- `audit_result/quality_level/from_type/from_type_norm`
- `indexes/image_indexes/multimodal_contents`
- `category_infos/primary_category`
- `tags/keywords`
- `task_id/flag`
- `insert_time/update_time/del_flag`

`flag` 是旧聊天 QA 批次字段；新任务写为与 `task_id` 相同的值，保证旧查询兼容。不得用 `flag` 替代或删除 `task_id`。

### 7.2 ext_info 历史兼容字段

基础字段：

- `from_file_name/from_page/from_chat_history/quality_info/tags`

2026-06 生产聊天 QA 已使用字段：

- `quality_reason`
- `knowledge_type`
- `business_tags/scenario_tags/entity_tags/es_tags`
- `reuse_scope/should_enter_reuse_evaluation/confidence/is_qualified`
- `source/source_quote/from_user/candidate_answer_time`
- `client/marketplace/model_platform`
- `supplement/supplement_mapping_error`

v17 已有审核与追溯字段继续保留：

- `review_decision/review_reason_codes/review_reason/review_model/review_version`
- `extractor_quality_level/grounded/knowledge_scope/sensitive/temporary/valid_until/auto_import`
- `source_message_ids/source_user_id/source_identity/source_identity_reason`

### 7.3 禁止无约束透传

- 只复制上述白名单字段。
- 输入中的未知顶层字段和未知 `ext_info` 子字段不得写入 ES。
- 本版本不新增 `info/reference_knowledge/evidence/upstream_payload` 等字段。
- 若未来需要新增字段，必须先定义名称、类型、生产者、消费者、空值语义和 mapping，再创建新 PRD 版本。

## 8. Category 兼容

优先级：

1. 候选上游已携带的 `category_infos`。
2. QA/webhook 携带的 category_name/category_id/category object。
3. task_info 携带的 category_name/category_id/category object。
4. 对 `payoneer_olive`，使用 `marketplace/model_platform` 作为 category_name 候选。
5. 模型平台字段未命中时，在实时类目树内用标签和问题原文精确匹配平台名。
6. 在当前 client 类目树中补 category_id/primary_category。
7. 无法解析时使用“默认分组”。

`platform/client/dataset` 始终保持客户值；平台名写入 category，不得覆盖客户归属。

## 9. 入库准入

自动入库必须同时满足：

```text
review_decision == accept
AND quality_level == high
AND grounded == true
AND sensitive == false
AND temporary == false
AND knowledge_scope != client_specific
```

条件不满足时不调用 embedding、查重或 ES 写入。实际写入前继续执行标题查重和 client/index 归属校验。

## 10. 统计契约

任务结果返回：

- `extracted_candidate_num`
- `high_candidate_num/mid_candidate_num/low_candidate_num`
- `review_accept_num/review_pending_num/review_reject_num`
- `insert_attempt_num/insert_success_num`
- `duplicate_skip_num/gate_skip_num/insert_failure_num`
- `qa_num`：与 `insert_success_num` 相同
- 抽取和审核两阶段 token/调用统计

`metrics_complete=false` 表示没有拿到入库器结果文件，不得用候选数推测入库数。

## 11. 失败、幂等与回滚

- 抽取失败：当前组任务失败，不推进 watermark。
- 审核单条失败：该条进入 review，不自动入库。
- schema/client 校验失败：阻断写入阶段。
- ES 写入异常：先写当前统计文件，再将任务标记失败。
- 查重命中：记录 duplicate_skip，不计入 qa_num。
- webhook 使用 `client + app_id + source_message_ids` 作为幂等基础。
- 回滚代码不修改存量 ES，无需迁移已有数据。

## 12. 验收标准

- v17 的身份、Turn、审核、准入、category 和统计测试继续通过。
- 2026-06 旧 QA 样本经过当前 schema 后，历史白名单字段逐项存在且值不变。
- 上游字段位于已有 `ext_info` 时，历史白名单字段仍能恢复。
- `supplement` 和 `supplement_mapping_error` 不丢失。
- 新任务同时写 `task_id` 与同值 `flag`，`flag` 保持 ES 顶层字段。
- 未知 `info/reference_knowledge/evidence` 和未知 ext_info 子字段不会写入 ES。
- 不修改任一 app 的在线或停用状态。

## 13. 发布流程

发布前：

- 更新远端并确认 main 无新提交。
- 运行语法检查、相关单测和完整可运行回归。
- 使用 2026-06 历史生产任务产物做字段逐项 dry-run 对照。
- 使用最近生产任务做候选到最终 ES schema 的字段覆盖检查。
- 确认没有聊天 QA 子任务运行后再更新 120。

发布后：

- 校验生产 commit 和 Python 3.9 导入。
- 常驻服务通过新子进程加载代码，无需因本版本改动账号状态。
- 下一次定时任务完成后，对首批实际 ES 文档执行字段存在性核对。
