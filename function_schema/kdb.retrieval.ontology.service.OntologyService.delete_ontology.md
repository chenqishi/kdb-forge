# kdb.retrieval.ontology.service.OntologyService.delete_ontology

## Signature

`OntologyService.delete_ontology(self, ontology_id: str, revision: Optional[int] = None) -> dict`

## Inputs

HTTP body.ontology_id；revision为HTTP body中的可选正整数。

## Outputs

200：deleted=true、ontology meta带del_flag=1；首次删除revision+1；已删再删message=本体已删除且revision不变（即使传旧revision）。不存在404；未删且revision不符409/current_revision。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
