# legacy_routes.modify_knowledge

## Inputs

旧 `ModifyKnowledgeRequest` 且 old_query_info 必填。

## Outputs

`ModifyKnowledgeResponse`；modifier 未配置时 HTTP 200、success=false。

## SQL

依赖外部 Dify；若注入则由其检索/写 ES8 Service。
