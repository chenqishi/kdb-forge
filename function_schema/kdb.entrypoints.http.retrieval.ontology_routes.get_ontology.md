# kdb.entrypoints.http.retrieval.ontology_routes.get_ontology

## Signature

`get_ontology(ontology_id: OntologyID, view: Literal['full', 'document', 'outline']='full', include_deleted: bool=False, service: OntologyService=Depends(get_service))`

## Inputs

路径ontology_id；view=full/document/outline，include_deleted默认false。 service经Depends(get_service)注入。

## Outputs

full: success/message/ontology含文档、投影、del_flag、document_bytes；document: 顶层success/message/ontology_id/revision/document；outline: ontology含ID/作用域/状态/revision/update_time及类、属性名、元素计数。非法view400，未删可见性不满足404。 路由仅传参/返回，文档业务规则交service；HTTP参数验证失败400 ONTOLOGY_BAD_REQUEST。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
