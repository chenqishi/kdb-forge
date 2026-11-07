# kdb.services.forge_compat.api.legacy_routes.modify_knowledge

## Signature

`modify_knowledge(request: ModifyKnowledgeRequest) -> ModifyKnowledgeResponse`

## Inputs

旧 `ModifyKnowledgeRequest` 且 old_query_info 必填。

## Outputs

`ModifyKnowledgeResponse`；modifier 未配置时 HTTP 200、success=false。

## SQL

依赖外部 Dify；若注入则由其检索/写 ES8 Service。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
