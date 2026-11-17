# kdb.retrieval.ontology.service.OntologyService.update_ontology_status

## Signature

`OntologyService.update_ontology_status(self, ontology_id: str, body: Any) -> dict`

## Inputs

HTTP body.ontology_id；body.status仅draft/active，revision为正整数。

## Outputs

200：meta，revision+1（同状态也增加），不重写文档。状态非法400；UPDATE=0时按ID回查，不存在/软删404，否则409/current_revision。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
