# scripts.scheduled.chat_mining.sh.alert_failure

## Inputs

失败阶段名称。

## Outputs

保持原chat-mining scheduler行为：stderr打印ALERT，尝试logger，logger失败不影响退出。scheduler失败步骤退出1，全部步骤成功才推进全局水位。

## SQL

无直接SQL。

## Source

`scripts/scheduled/chat_mining.sh`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
