# legacy_routes.modify_knowledge_direct_update

## Inputs

旧 `ModifyKnowledgeRequest`。

## Outputs

`ModifyKnowledgeResponse`；modifier 未配置时 HTTP 200、success=false，避免伪造已修改。

## SQL

依赖外部 Dify；若注入则由其写 ES8 Service。
