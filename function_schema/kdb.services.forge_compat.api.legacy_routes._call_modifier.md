# kdb.services.forge_compat.api.legacy_routes._call_modifier

## Signature

`_call_modifier(method_name: str, request: ModifyKnowledgeRequest) -> Any`

## Inputs

方法名与旧 `ModifyKnowledgeRequest`。

## Outputs

调用注入 modifier 的旧关键字参数；未注入抛 RuntimeError。

## SQL

外部 Dify 依赖；不读写 SQL。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
