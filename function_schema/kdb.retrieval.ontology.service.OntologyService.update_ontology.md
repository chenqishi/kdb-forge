# kdb.retrieval.ontology.service.OntologyService.update_ontology

## Signature

`OntologyService.update_ontology(self, ontology_id: str, body: Any) -> dict`

## Inputs

body.ontology_id为32位小写hex，data_json为完整文档，revision为正整数；status可选且缺省保留，review_status可选且缺省重置pending。

## Outputs

200：success/message/ontology meta，含两个状态，不返回data_json。不存在/已删404；禁止改变client/product（409），允许改名但事务内判重。正文与两个状态同一UPDATE写入，成功revision+1；旧revision返回409/current_revision。缺省重新待审，可显式指定审核结果。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
