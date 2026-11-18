# kdb.retrieval.ontology.service.OntologyService.delete_ontology

## Signature

`OntologyService.delete_ontology(self, ontology_id: str, revision: Optional[int]=None) -> dict`

## Inputs

body.ontology_id；body.revision为可选正整数。任意审核/生效状态均可软删。

## Outputs

200：deleted=true、ontology meta带del_flag=1和两个原状态；首次软删revision+1，审核/生效状态不变。已删再删message=本体已删除，revision不变，即使携带旧revision。不存在404，未删且版本不符409。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
