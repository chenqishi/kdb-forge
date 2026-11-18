# kdb.retrieval.ontology.service.OntologyService.get_ontology

## Signature

`OntologyService.get_ontology(self, ontology_id: str, view: str='full', include_deleted: bool=False, audit_status: str='approved') -> dict`

## Inputs

body.ontology_id；query的view=full/document/outline默认full、include_deleted默认false、audit_status默认approved，可传pending/rejected/all。

## Outputs

默认只返回未删且approved的记录；审核与软删筛选独立，all仅放开审核条件，不满足返回404。full含元数据、文档、del_flag、document_bytes；document顶层含ontology_id/status/audit_status/revision/document；outline含作用域、两个状态、版本、更新时间、类/属性和计数。非法view或审核筛选400。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
