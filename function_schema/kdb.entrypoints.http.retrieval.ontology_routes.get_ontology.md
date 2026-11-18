# kdb.entrypoints.http.retrieval.ontology_routes.get_ontology

## Signature

`get_ontology(body: GetOntologyRequest, view: Literal['full', 'document', 'outline']='full', include_deleted: bool=False, review_status: Annotated[ReviewFilter, Query(description='默认仅审核通过；pending/rejected筛选待审/驳回，all查看所有审核状态')]='approved', service: OntologyService=Depends(get_service))`

## Inputs

body.ontology_id；query的view=full/document/outline默认full、include_deleted默认false、review_status默认approved，可传pending/rejected/all。 service经Depends(get_service)注入。

## Outputs

默认只返回未删且approved的记录；审核与软删筛选独立，all仅放开审核条件，不满足返回404。full含元数据、文档、del_flag、document_bytes；document顶层含ontology_id/status/review_status/revision/document；outline含作用域、两个状态、版本、更新时间、类/属性和计数。非法view或审核筛选400。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
