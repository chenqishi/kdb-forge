# kdb.retrieval.ontology.service.OntologyService.update_ontology

## Signature

`OntologyService.update_ontology(self, ontology_id: str, body: Any) -> dict`

## Inputs

HTTP body.ontology_id为32位小写hex；body.data_json完整文档，revision为正整数，status可选（缺省保留当前状态）。

## Outputs

200：success/message/ontology meta，不含data_json。先查现行，不存在/软删404；校验文档后禁止改变client/product（409/current与requested），允许改名但仓储判重。UPDATE rowcount=0时按ID回查，区分404/409/current_revision。成功revision+1。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
