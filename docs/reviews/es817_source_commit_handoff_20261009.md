# ES8 source 修复提交交付

2026-10-09，用户在完成验证后明确要求“提交推送”。本次授权范围为将旧项目的代码、测试、schema 和验收报告提交推送到 main；生产 git pull、上线、服务重启和运行配置修改仍须另有当次明确指令。

交付基线 `12a86da7163c5136524a60730c6af476788933c5`。ES8 引擎修复后 SHA256 为 `523e62a94c03d6d94d785210495245bd78cd0cd881532b7dd8166d77bdc1afca`，已再次核验与真实测试执行版本相同，没有为了提交改实现。

修复恢复 dual 的请求级 source 策略、完整路径 inner_hits 请求、文本/图片向量回填及合并，并保持异常 fallback 的 source 策略；原业务调用、根向量、native KNN、路由和批量并发上限不变。实现与行为回归见 [修复报告](es817_source_compat_fix_20261009.md)。

最直接的本次验收是 [同 ES8 召回对照](es817_source_recall_only_20261009.md)：修改前后同库、同输入，PaaS/Serverless 各 100 个 query，ES 原始每路及合并候选 ID/顺序/score/total、实际查询条件和预算全部严格相同。410 次真实只读请求，0差异/错误/违规，线上状态前后不变。引擎回归 325 passed、2 个既有 xfailed；召回比较器另有 11 passed。

此前的 ES7/ES8 91/100、88/100 完整响应对照是另一个验收范围，不用于解释本次 source 修改是否改变召回。原报告中的“未提交推送”描述验证时的现场；本文件记录之后收到的代码发布授权，并不代表获得生产部署或重启授权。

可复用测试和只读工具、对应 schema、报告及原始 SHA manifest 一并提交。完整 JSONL/响应证据、JUnit 运行输出、重复尝试目录、私有 query/原文/向量、数据快照和既有配置保留在 `/root/knowledge_database_builder-es817-release-20261009`，不随此次提交入库。因此报告中的完整证据链接和 manifest 所列部分 artifact 是本机留存证据，不是在仓库中缺失的实现依赖；工具默认读取的私有 fixture 也不提交。

仓库可见的验证摘要及留存证据 SHA 见 [提交验证摘要](es817_source_commit_validation_20261009.json)。源码提交标识以 git 历史和本会话的推送结果为准。
