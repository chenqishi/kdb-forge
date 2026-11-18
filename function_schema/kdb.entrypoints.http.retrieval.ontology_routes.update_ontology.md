# kdb.entrypoints.http.retrieval.ontology_routes.update_ontology

## Signature

`update_ontology(body: UpdateOntologyRequest, service: OntologyService=Depends(get_service))`

## Inputs

body.ontology_id为32位小写hex，data_json为完整文档，revision为正整数；status可选且缺省保留，review_status可选且缺省重置pending。 service经Depends(get_service)注入。

## Outputs

200：success/message/ontology meta，含两个状态，不返回data_json。不存在/已删404；禁止改变client/product（409），允许改名但事务内判重。正文与两个状态同一UPDATE写入，成功revision+1；旧revision返回409/current_revision。缺省重新待审，可显式指定审核结果。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
