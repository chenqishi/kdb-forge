# kdb.retrieval.ontology.service.OntologyService.get_ontology

## Signature

`OntologyService.get_ontology(self, ontology_id: str, view: str = "full", include_deleted: bool = False) -> dict`

## Inputs

HTTP body.ontology_id；view=full/document/outline，include_deleted默认false。

## Outputs

full: success/message/ontology含文档、投影、del_flag、document_bytes；document: 顶层success/message/ontology_id/revision/document；outline: ontology含ID/作用域/状态/revision/update_time及类、属性名、元素计数。非法view400，未删可见性不满足404。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
