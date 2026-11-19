---
name: knowledge-dedup
description: 对指定知识索引执行重复与冲突检查，支持增量知识和整篇文档，供管理员的 leader 场景使用。
---
# knowledge-dedup

## 用途
在 sell_agents 的 skill_agent 中组织知识去重工作。工具提供检查与处理能力，本技能不实现另一个 Agent。

## 何时使用
管理员要求查找重复、冲突、处理未审核新增知识，或替换重复文档时使用。部署默认关闭；只允许 admin 的 leader 场景。

## 使用规则
- 先确定一个具体 index、qa 或 segment、时间范围和处理策略。不同类型分别执行；不按 platform/账号隔离。工具权限以服务器认证为准，不能通过参数宣称自己是 admin。
- 非交互模式：沿初始任务执行，缺少必需信息、没有权限或工具失败时说明具体原因，不等待用户回复。未指定处理策略时使用 record_only，写检查结果而不修改正文/删除知识。
- 交互模式：已明确的部分继续执行；确需用户选择时输出待答问题并结束当前轮，下一轮带会话上下文继续。不要把等待结果写成成功，也不要重复请求已经给过的授权。
- 先用 knowledge_dedup_select 确定增量范围和估算 token。例如“marsmind 自10月19日新增、未去重、未审核”的范围：index=marsmind、since=带年份的日期、only_unchecked=true、unaudited=true，qa/segment各跑一次。年份不明且上下文不能确定时不要猜测。
- 快速检查用 knowledge_dedup_fast；批量精查用 knowledge_dedup_run。dry_run=true仅预览；任务已授权记录/处理时用dry_run=false及指定policy。大批量逐批处理；selection_truncated=true说明仍有未处理范围。
- 深入查找时可改写主题/对象/条件，用 knowledge_dedup_recall 发起新一轮召回，再把候选ID交给 knowledge_dedup_compare 验证。不要无限重复同一查询；候选不再增加或已达到任务成本限制时停止并说明边界。
- relevance_score 是相关性分数，不是重复概率；默认阈值是保守起始值。必要时降低threshold、把min_shared_topics设为0，再验证漏掉的改写表达。不得只凭重排分数删除知识。
- duplicate表示完整等价；overlap表示包含或部分重叠，仍可能有独立信息；different表示本轮未发现重复/冲突，也可能同主题，不写入similarity_info；uncertain需要核实，不能据此自动删除/改写。
- evidence必须能在两侧原文中找到。政策版本、适用时段、地区或流程条件不清的相反说法列为uncertain；入库时间不能证明政策生效时间。ChatQA抽取可能丢失前文条件，应先查看来源上下文，不能拿一般规则覆盖条件不全的个案。
- record_only仅记录；keep_new/keep_old按入库时间保留新/旧的完整重复项。确认冲突时使用新知识修订旧内容并重新置待审；overlap/uncertain不自动删。混合结果、失败和并发变更必须明确报告，不能概括为全部完成。
- 文档检查用 knowledge_dedup_document：名称主体相同或同一文件的segment覆盖>=70%即命中。skip_new跳过新文档；replace_old软删匹配旧文档的全部qa/segment，不能当成逐条QA精细处理。任务已要求替换才执行replace_old；文档管道会在新知识入库验证后完成替换。
- 最终给出新增知识ID、相似ID、关系、原因/证据、实际动作、失败/待核实项和模型token；不能把估算当实测，不能把模型检查完成当审核通过。

## Scope
admin_system

## Category
knowledge

## ApplicableScopes
role:leader

## Tools
knowledge_dedup_select
knowledge_dedup_recall
knowledge_dedup_fast
knowledge_dedup_run
knowledge_dedup_compare
knowledge_dedup_document
