# kdb.entrypoints.http.retrieval.ontology_routes.delete_ontology

## Signature

`delete_ontology(body: DeleteOntologyRequest, service: OntologyService=Depends(get_service))`

## Inputs

body.ontology_id；body.revision为可选正整数。任意审核/生效状态均可软删。 service经Depends(get_service)注入。

## Outputs

200：deleted=true、ontology meta带del_flag=1和两个原状态；首次软删revision+1，审核/生效状态不变。已删再删message=本体已删除，revision不变，即使携带旧revision。不存在404，未删且版本不符409。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
