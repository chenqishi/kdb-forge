# 聊天 QA 自动学习 PRD v20260905-v20

## 1. 产品目标

knowledge_database_builder 从客户群聊中沉淀可复用业务知识，写入当前客户的 ES 知识库。系统必须同时满足：

- 只把真实人类同事的回复作为答案来源。
- 发言人名称包含独立 `AI` 标识时，不得成为答案来源。
- 一条知识的答案只能来自当前 answer-source Turn。
- 同一发言人 180 秒内回复合并，向前最多携带 50 句上下文。
- 候选抽取与入库质量审核使用独立模型请求。
- 每个客户使用“通用 Prompt + 当前客户差异 Prompt”；没有客户模板时安全回落通用版。
- 只有 `accept + high + grounded` 且非敏感、非临时、非客户个案的知识可自动入库。
- 尽量保留同事原话，不用历史答案或常识扩写当前 Turn。
- 保留历史生产字段和 category 写入能力，不增加 ES 字段。
- 不修改任一 app 的登录、在线、停用或回复状态。

## 2. 版本背景

v19 已上线 answer-source Turn、客户 Prompt 路由和独立入库审核。v20 解决一个前置身份漏洞：

- 生产通讯录将 `Wayfair AI助理(运营指导)` 标记为同事。
- 旧 system prompt 的同事名单也可能包含该账号。
- Turn 构建因此会把 AI 回复当作当前答案，再交给抽取模型。
- v19 reviewer 已能对 `AI助理/智能助理/机器人/bot` 做确定性拒绝，但这是二阶段保护，不应替代前置 Turn 筛选。

2026-09-05 生产只读核对显示，`wayfair_test` 现存 38 条 high 自动学习 QA 中，36 条当前答案来源明确为 `Wayfair AI助理(运营指导)`。v20 的目标是阻止同类新候选产生，不在本版本自动修改历史 ES。

## 3. 范围与非目标

### 3.1 本版本修改

- 新增发言人名称 `AI` 关键词判定。
- 从 system prompt 解析同事名单时，移除命中该关键词的账号。
- 身份推断时将该规则作为硬 veto，优先级高于白名单、平台同事名单和通讯录同事标记。
- 保留 reviewer 已有 AI 答案来源硬拒绝，形成前后两层保护。
- 增加实例化单元测试和生产样本回放。

### 3.2 本版本不修改

- 不修改通讯录、app 或账号在线/停用状态。
- 不改变人类同事的现有身份优先级。
- 不改变 180 秒合并、50 句上下文和 Turn 边界。
- 不改变抽取、审核、category、schema、embedding、去重和 ES 写入约定。
- 不在发布流程中删除或修改历史知识。

## 4. AI 关键词判定

### 4.1 匹配规则

`AI` 按大小写不敏感的独立 ASCII 关键词匹配：

```regex
(?i)(?<![A-Za-z])ai(?![A-Za-z])
```

应命中：

- `Wayfair AI助理(运营指导)`
- `AI客服`
- `wayfair-ai-bot`
- `ai_01`

不应命中：

- `Aimee Hu`
- `Daisy`
- `Kai`
- `Paid Support`

不使用简单子串 `"ai" in name.lower()`，因为会误伤真人姓名。

### 4.2 身份优先级

最终判定次序：

1. 通讯录显式静默 → `未识别/不能作为答案来源`，并保留原静默原因。
2. 姓名命中独立 `AI` 标识 → `未识别/不能作为答案来源`。
3. 群白名单 → leader 答案来源。
4. 平台同事名单 → 同事答案来源。
5. 通讯录身份 → 对应角色。
6. 少量平台身份前缀规则。
7. 未命中 → 客户/问题来源。

AI veto 只阻止其成为知识答案锚点；该消息仍可在有人类答案 Turn 时作为上下文参考，但不得进入 `a/source_quote`。

## 5. Answer-source Turn

- 只以 `leader/可作为答案来源` 或 `同事/可作为答案来源` 的消息为锚点。
- 同一稳定发送人 ID 在 180 秒内的连续回复可合并。
- 客户插话、换人或超时结束当前 Turn。
- 向前最多携带 50 句还原问题。
- 答案只能来自当前 Turn，不得使用上下文中的历史答案。
- 名称命中 AI veto 的消息不能开启或并入 answer-source Turn。

## 6. Prompt 路由

抽取 Prompt：

```text
extract.default.md
+ extract.<normalized_client>.md
```

审核 Prompt：

```text
review.default.md
+ review.<normalized_client>.md
```

当前日常任务客户：

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

未知客户或客户模板缺失时只使用通用版，不串用其它客户模板。

## 7. 两阶段处理

### 7.1 阶段 A：候选抽取

- 输入只包含当前人类答案 Turn 和向前 50 句上下文。
- 输出 q/a、source/source_quote、来源身份、平台、质量信号和追溯信息。
- 稳定规则、流程、条件和方法可抽取。
- 临时活动、个案、内部协作、敏感信息、无实质答案和上下文不足时返回空。
- a 尽量保留人类同事原话，只做最小清理。

### 7.2 程序硬过滤

二次模型前拒绝：

- AI 助理、智能助理、机器人、bot 或明确非人工答案来源。
- 损坏核心对象的脱敏占位符。
- 未脱敏邮箱、手机号和超长可定位编号。

硬拒绝不消耗第二次模型请求。

### 7.3 阶段 B：独立审核

审核模型只判定 `decision/quality_level/grounded/knowledge_scope/sensitive/temporary/valid_until/reason_codes/reason`，不修改 q/a。返回不可解析或请求失败时 fail closed 为 `review + mid`。

## 8. ES 与 Category 契约

本版本不增加、删除或更名 ES 字段。保留：

- 顶层 `title/content/synonyms_title/data_type/platform/client/dataset/audit_result/quality_level/from_type/from_type_norm/indexes/image_indexes/multimodal_contents/category_infos/primary_category/tags/keywords/task_id/flag/insert_time/update_time/del_flag`。
- `ext_info` 既有白名单字段，包括 source、source_quote、candidate_answer_time、supplement、review_decision、source_message_ids 等。
- category 继续按“候选已有 → QA/webhook → task_info → Payoneer Olive marketplace → 类目树精确匹配 → 默认分组”解析。
- `platform/client/dataset` 始终表示客户归属，真实平台名进入 category。

## 9. 入库准入与统计

自动入库必须同时满足：

```text
review_decision == accept
AND quality_level == high
AND grounded == true
AND sensitive == false
AND temporary == false
AND knowledge_scope != client_specific
```

条件不满足时不调用 embedding、查重或 ES 写入。`qa_num` 等于真实成功入库数；候选数、审核数和入库数分开统计。

## 10. 失败、幂等与历史数据

- 抽取失败：当前组失败，不推进 watermark。
- 审核失败：候选进入 review，不自动入库。
- 客户 Prompt 缺失：回落通用版并记录未命中。
- 重试或重跑仍使用已有去重与写入契约。
- v20 发布不修改历史 ES。历史 AI 回流知识需使用独立清理批次、`del_flag=1` 软隔离和 rollback 清单，不与代码发布绑定。

## 11. 验收标准

- `Wayfair AI助理(运营指导)` 即使同时存在于通讯录同事和旧 prompt 名单，也不能构建 answer-source Turn。
- 从 prompt 提取同事名单时，命中独立 `AI` 关键词的名称不在结果中。
- `Aimee Hu`、`Daisy`、`Kai` 不被误判为 AI 账号。
- 同一组聊天中 AI 回复被排除，真人 `Wei Wang` 回复仍能构建 Turn。
- reviewer 的 `ai_answer_source` 硬拒绝回归仍通过。
- v19 的 Turn、Prompt 路由、category、字段兼容、两阶段审核和入库统计测试全部通过。
- 不修改 app 或账号在线/停用状态，不在测试中写生产 ES。

## 12. 发布与回滚

发布前：

- fetch 远端并确认 main 同步、无冲突。
- 检查工作树，不覆盖无关用户文件。
- 执行语法检查、AI 关键词单测和聊天 QA 相关回归。
- 用 Wayfair 生产样本只读回放，确认 AI Turn 数为 0。
- 确认生产没有正在执行的聊天 QA 子任务。

发布：

- 提交并推送 main。
- 120 使用 `git pull --ff-only` 更新。
- 运行生产 Python 语法、导入和目标测试。
- 常驻调度服务继续运行，新任务子进程自动加载新代码，不修改账号状态。

回滚：

- 代码回滚到 v19 commit 即恢复原身份判定。
- 本版本不修改 schema 或存量 ES，无数据迁移回滚。
