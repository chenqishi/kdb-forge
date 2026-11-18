# kdb.retrieval.ontology.service.OntologyService.update_ontology_status

## Signature

`OntologyService.update_ontology_status(self, ontology_id: str, body: Any) -> dict`

## Inputs

body.ontology_id、正整数revision；status=active/inactive和review_status=pending/approved/rejected均可选，至少提供一个非null值。未传状态保留。

## Outputs

200：meta含两个状态，单次成功revision+1（相同值也增加），不重写文档。审核和启停可独立更新，未提供的字段保持原值；启停改变不重置审核。状态非法或空更新400；UPDATE=0回查区分404与409/current_revision。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
