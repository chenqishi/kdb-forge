---
name: 自动审核验收样本不能变成生产client限制
type: feedback
description: 先验收payoneer_olive不授权缩小原all范围，生产审核保持原全量client范围。
---

2026-10-19 用户纠正“自动审核 cron 已限定为 payoneer_olive？为啥，突然限定client”。本次错误是把“先对一个索引做验收”的建议落实成了生产 cron 的 client 白名单，未经用户要求改变原 all 语义。

执行规则：验证样本可通过 dry-run 的 --index 指定；上线时保持原审核目标、来源、24h阈值及质量规则。不要将样本范围写进生产环境变量或cron。若确实需要改变审核策略/范围，先说明具体影响并按用户当次要求执行。

本次已于14:35恢复all，原先短暂限制在下一轮15:00任务前撤销，未触发受限执行。不要再沿用早期“首次仅Olive”部署建议；运行两个provider按现有Router归属全量枚举，109项dry-run失败0。审计文档见 docs/reviews/auto_audit_main_deployment_and_entry_audit_20261019.md。
