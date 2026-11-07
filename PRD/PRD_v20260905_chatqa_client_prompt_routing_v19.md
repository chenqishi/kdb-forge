# 聊天 QA 自动学习 PRD v20260905-v19

## 1. 产品目标

knowledge_database_builder 从客户群聊中沉淀可复用业务知识，写入当前客户的 ES 知识库。系统必须同时满足：

- 只把真实人类同事的回复作为答案来源。
- 一条知识的答案只能来自当前 answer-source Turn。
- 候选抽取与入库质量审核使用独立模型请求。
- 每个客户使用“通用 Prompt + 当前客户差异 Prompt”，没有客户模板时安全回落通用版。
- 只有审核为 `accept + high` 的知识才可自动入库。
- 临时、个案、敏感、错误脱敏和 AI 回复不得进入长期知识库。
- 尽量保留同事回复原话，不用历史答案或常识扩写当前 Turn。
- 保留历史生产聊天 QA 已有的来源、证据、时间、标签和图片补充字段。
- 不增加 ES 字段，不修改任一 app 的在线或停用状态。
- 客户、应用、索引和 category 必须严格隔离并可追溯。
- `qa_num` 必须代表真实成功入库数。

## 2. 范围与非目标

本版本影响 `chat_qa_mining` 的定时批处理，也为未来 webhook 单 Turn 处理复用同一 Prompt 路由。

本版本只修改：

- Direct LLM 抽取器的 Prompt 加载链路；
- 通用抽取 Prompt；
- 当前生产定时客户的抽取和审核差异 Prompt；
- Prompt 命中与 hash 的运行统计；
- 对应测试、PRD 和设计规范。

本版本不改变：

- app 在线、停用、删除和回复能力状态；
- answer-source 身份优先级与静默账号 veto；
- 同人 180 秒合并、向前 50 句和 Turn 边界；
- 程序硬过滤、二阶段模型调用和自动入库闸门；
- schema、ES mapping、字段白名单、category 解析和统计口径；
- 文档、HTML、Excel 的 QA/segment 导入流程；
- 存量 ES 知识及历史任务结果。

## 3. 生产现状与根因

2026-09-05 上线前核对：

- 生产已运行 answer-source Turn：以人类同事回复为锚点，同一发送人 180 秒内合并，向前最多 50 句，答案只来自当前 Turn。
- Direct LLM 抽取器始终返回代码内嵌的同一份通用 Prompt，忽略已读取的客户业务 Prompt。
- 批任务数据已经包含 client，但 `run_batch_robot_chat_data` 没有把 client 传给 `DirectLLMJsonRequest`。
- 仓库虽有 `extract.joint_login.md`，生产 Direct LLM 主链路没有加载它；其它定时客户也没有自己的抽取模板。
- 审核器已经具备 `review.default + review.<client>` 的加载能力，但上线前没有客户审核模板。
- 最近一个月共有 10 个 client、38 个 app 进入每日任务；其中 0 个 app 配置 `chat_qa_mining_prompt`。因此客户差异必须由版本化仓库模板兜底，不能依赖逐账号补配置才能生效。

五轮、每轮五个 Turn 的上线前抽样结果：

- 25/25 抽取请求成功，覆盖 8 个 client。
- 旧 Prompt 仅形成 6 个标准候选、2 个进入审核、0 个自动入库。
- 存在明确漏抽：`joint_login` 中“没有销售额也需要截图发一下”被当成普通索要截图，实际在明确申报上下文中表达“零销售额仍需提交截图”的稳定规则。
- 简单追加一段全局规则使输入 token 增加约 14.1%，候选反而从 6 降到 1，说明应缩短通用 Prompt，并将客户校准拆成差异模板。

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

任务侧 prompt 文件继续用于解析可作为答案来源的同事姓名。它不作为业务抽取 Prompt，避免自动生成的长名单和历史自由文本覆盖版本化规则。

## 5. 身份与 Answer Turn

### 5.1 身份角色

- `leader/可作为答案来源`
- `同事/可作为答案来源`
- `客户/只能作为问题来源`
- `未识别/不能作为答案来源`

通讯录中静默/不可作为答案源的账号具有 veto 权，覆盖旧 prompt 的过期名单。AI 助理、智能助理、机器人和自动回复不得作为答案来源。本配置只影响知识学习，不改变 app 的在线或停用状态。

### 5.2 Turn 规则

- 以可作为答案来源的消息为锚点。
- 同一稳定发送人 ID 在 180 秒内连续回复可合并。
- 客户插话、换人或超时结束当前 Turn。
- 向前最多携带 50 句作为问题上下文。
- 答案不得使用上下文中的其它历史回复。

## 6. Prompt 路由

### 6.1 抽取阶段

最终 Prompt 按固定次序组成：

```text
extract.default.md
+ extract.<normalized_client>.md（存在时）
```

规则：

- client 仅允许小写字母、数字和下划线；连字符规范为下划线；非法 client 不参与文件解析。
- 客户模板存在时追加到通用模板之后，客户差异规则优先。
- 客户模板不存在时只使用通用模板，不读取相似名称或其它客户模板。
- 通用模板读取失败时回落代码内嵌 Prompt，任务不中断；错误写日志。
- 记录 client、`client_prompt_applied` 和最终 `prompt_hash`，不写入 ES。

### 6.2 审核阶段

最终 Prompt 按固定次序组成：

```text
review.default.md
+ review.<client>.md（存在时）
```

审核只判定，不修改 q/a；审核版本为 `chat_qa_review_v2_client_prompt`。

### 6.3 当前客户模板覆盖

每日任务当前覆盖 10 个 client：

- `joint_login`
- `mars_mind`
- `mercado`
- `mercado_local`
- `payoneer`
- `payoneer_olive`
- `qooten`
- `serene_demo_client`
- `wayfair`
- `wayfair_test`

每个 client 都必须同时存在 `extract.<client>.md` 和 `review.<client>.md`。模板只表达已有业务证据中的边界，不编造客户政策；证据不足的客户模板用于约束租户名不得被误当作平台名。

## 7. 两阶段模型管道

### 7.1 阶段 A：候选抽取

输入为当前 Turn 与向前 50 句。输出 q/a、source_quote、来源身份、平台、质量信号和追溯 ID。

抽取原则：

- 稳定规则、流程、条件和方法可以抽。
- 明确短规则不能因字数少而丢弃。
- a 尽量保留原话，只做称呼、寒暄、引用包装、敏感信息和无关尾巴的最小清理。
- 混有敏感或个案内容时，只允许截取当前 Turn 中连续、完整、自洽的安全规则原文；不能安全切分则不抽。
- 当前 Turn 不完整、指代不清、临时、个案或需要猜测时返回空。

抽取器的 high/mid/low 只是候选信号，不能直接决定入库。

### 7.2 程序硬过滤

第二模型之前拒绝高确定性风险：

- AI 助理、机器人或明确非人工答案身份；
- 损坏核心对象的脱敏占位符；
- 未脱敏邮箱、手机号和超长可定位编号。

硬拒绝不消耗第二次模型请求。

### 7.3 阶段 B：独立审核

审核模型只判断 `decision/quality_level/grounded/knowledge_scope/sensitive/temporary/valid_until/reason_codes/reason`，不修改 q/a。返回不能解析或请求失败时 fail closed 为 `review + mid`。

## 8. ES 字段契约

本版本不增加、删除或更名任何 ES 字段。

### 8.1 顶层字段

保留：

- `title/content/synonyms_title/data_type`
- `platform/client/dataset`
- `audit_result/quality_level/from_type/from_type_norm`
- `indexes/image_indexes/multimodal_contents`
- `category_infos/primary_category`
- `tags/keywords`
- `task_id/flag`
- `insert_time/update_time/del_flag`

### 8.2 ext_info 历史兼容字段

保留基础字段、2026-06 生产聊天 QA 已有字段和 v17/v18 审核追溯字段，包括 `source/source_quote/candidate_answer_time/supplement/review_decision/source_message_ids` 等既有白名单。

未知 `info/reference_knowledge/evidence/upstream_payload` 和未知 ext_info 字段不得写入 ES。Prompt 版本与 hash 只进入运行统计，不借本版本增加 ES 字段。

## 9. Category 兼容

category 继续沿用 v18 优先级：

1. 候选已有 `category_infos`；
2. QA/webhook 的 category_name/category_id/category object；
3. task_info 的对应字段；
4. `payoneer_olive` 的 `marketplace/model_platform`；
5. 当前 client 类目树内的精确平台名匹配；
6. 无法解析时进入“默认分组”。

`platform/client/dataset` 始终是客户归属，平台名进入 category，不得覆盖租户。

## 10. 入库准入与统计

自动入库必须同时满足：

```text
review_decision == accept
AND quality_level == high
AND grounded == true
AND sensitive == false
AND temporary == false
AND knowledge_scope != client_specific
```

条件不满足时不调用 embedding、查重或 ES 写入。`qa_num` 继续等于 `insert_success_num`；候选数、审核数和真实写入数分别统计。

## 11. 失败、幂等与回滚

- 抽取失败：当前组失败，不推进 watermark。
- 审核失败：当前候选进入 review，不自动入库。
- Prompt 客户模板缺失：回落通用模板并记录未命中，不串用其它客户模板。
- 通用文件读取失败：使用内嵌通用 Prompt 并记录错误。
- ES 写入和去重保持 v18 语义。
- 回滚代码不修改存量 ES，无需数据迁移；回滚后新子进程恢复旧 Prompt 行为。

## 12. 验收标准

- 10 个每日任务 client 均有抽取和审核模板。
- `joint_login` 最终 Prompt 同时包含通用模板与 joint_login 差异，不包含其它客户模板。
- 未知/非法 client 只使用通用模板。
- 批任务把数据映射中的 client 传给 Direct LLM 抽取器。
- 任务侧长同事名单不重复进入业务 system prompt，身份解析能力不变。
- 同一 25 个 Turn 回归无请求失败；明确零销售额材料规则得到候选并通过或至少进入独立审核。
- AI、临时、活动、个案和敏感样本不得新增自动入库。
- v18 身份、Turn、审核、category、字段兼容和统计测试全部通过。
- 不修改任一 app 的在线或停用状态，不执行测试 ES 写入。

## 13. 发布流程

发布前：

- fetch 远端并确认 main 同步、无冲突；
- 语法检查、Prompt 路由测试、相关单测和全量测试；
- 使用同一 25 个生产 Turn 做候选和审核 dry-run，只读数据、不写 ES；
- 确认生产工作树干净且没有聊天 QA 子任务运行。

发布：

- 合并并推送 main；
- 120 使用 `git pull --ff-only` 更新；
- 生产 Python 3.9 做语法和导入检查，Python 3.10 跑目标测试；
- 常驻调度服务继续运行，新任务子进程自动加载新代码，无需修改账号状态或重启账号。

发布后：

- 校验生产 commit；
- 对 10 个 client 检查 `client_prompt_applied=true` 且 hash 可追溯；
- 下一次正常定时任务后核对候选、审核、真实入库统计和样例质量。
