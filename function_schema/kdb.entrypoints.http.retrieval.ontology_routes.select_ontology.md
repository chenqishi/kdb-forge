# kdb.entrypoints.http.retrieval.ontology_routes.select_ontology

## Signature

`select_ontology(body: SelectOntologyRequest, service: OntologyService = Depends(get_service))`

## Inputs

client/product小写作用域编码，默认空串；name可选精确过滤（None/空串不筛选）；include_document默认true。 service经Depends(get_service)注入。

## Outputs

success/message/scope/fallback/request/ontology。无行200、scope=none、fallback=true、ontology=null；有行按实际client/product计算scope，fallback=(实际作用域!=请求)。include_document=true返回该行完整data_json，false返回outline；永不合并。 路由仅传参/返回，文档业务规则交service；HTTP参数验证失败400 ONTOLOGY_BAD_REQUEST。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
