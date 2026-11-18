# kdb.entrypoints.http.retrieval.ontology_routes.select_ontology

## Signature

`select_ontology(body: SelectOntologyRequest, service: OntologyService=Depends(get_service))`

## Inputs

client/product默认空串；name可选精确匹配；include_document默认true。不提供绕过审核、生效或软删条件的参数。 service经Depends(get_service)注入。

## Outputs

success/message/scope/fallback/request/ontology。只选未删、active且approved的整行；待审、驳回或停用客户行回落符合条件的上层行。无匹配200/ontology=null/scope=none/fallback=true；有匹配按实际作用域计算fallback。文档/outline视图均含两个状态，永不合并。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
