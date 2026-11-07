# kdb.services.forge_compat.engine.RoutedLegacyEngine

## Inputs

继承 EsSearchInterfaceES8 的当前引擎构造参数。严格计数接收单索引、query 与 require_complete。

## Outputs

其他行为继承唯一 ES8 实现。require_complete=True 时传 ignore_unavailable=False、allow_no_indices=False、expand_wildcards=none，使用 complete_count 校验响应。

## SQL

无 SQL；严格计数仅 ES _count 读取，不创建索引。

## Source

`src/kdb/services/forge_compat/engine.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
