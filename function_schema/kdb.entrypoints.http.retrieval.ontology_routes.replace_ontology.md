# kdb.entrypoints.http.retrieval.ontology_routes.replace_ontology

## Signature

`replace_ontology(ontology_id: OntologyID, body: ReplaceRequest, service: OntologyService=Depends(get_service))`

## Inputs

路径ontology_id为32位小写hex；body.data_json完整文档，revision为正整数，status可选（缺省保留当前状态）。 service经Depends(get_service)注入。

## Outputs

200：success/message/ontology meta，不含data_json。先查现行，不存在/软删404；校验文档后禁止改变client/product（409/current与requested），允许改名但仓储判重。UPDATE rowcount=0时probe，区分404/409/current_revision。成功revision+1。 路由仅传参/返回，文档业务规则交service；HTTP参数验证失败400 ONTOLOGY_BAD_REQUEST。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
