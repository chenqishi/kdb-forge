# kdb.entrypoints.http.retrieval.ontology_routes.update_ontology

## Signature

`update_ontology(body: UpdateOntologyRequest, service: OntologyService=Depends(get_service))`

## Inputs

body.ontology_id为32位小写hex，revision为正整数；data_json可省略，提供时必须是完整文档且不能为null。status、audit_status可选；至少提供文档或一个非null状态。仅更新状态时保留未传字段和文档，更新正文时未传audit_status默认重置pending（未审核）。 service经Depends(get_service)注入。

## Outputs

200：success/message/ontology meta，含两个状态，不返回data_json。不存在/已删404；禁止改变client/product（409），允许改名但事务内判重。统一更新正文、生效或审核状态；省略data_json时只更新指定状态，不重写文档。提供正文时仍校验文档及作用域，审核状态缺省重置为未审核，可显式指定。每次成功revision+1；旧revision返回409/current_revision，空更新400，显式null文档422。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
