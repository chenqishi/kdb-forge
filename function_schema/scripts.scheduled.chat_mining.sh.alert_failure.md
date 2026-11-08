# scripts.scheduled.chat_mining.sh.alert_failure

## Inputs

失败阶段名称。

## Outputs

保持原chat-mining scheduler行为：stderr打印ALERT，尝试logger，logger失败不影响退出。scheduler失败步骤退出1，全部步骤成功才推进全局水位。

## SQL

无直接SQL。

## Source

`scripts/scheduled/chat_mining.sh`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
