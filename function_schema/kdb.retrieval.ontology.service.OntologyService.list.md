# kdb.retrieval.ontology.service.OntologyService.list

## Signature

`OntologyService.list(self, client=None, product=None, status=None, q=None, deep=False, include_deleted=False, page=1, page_size=20) -> dict`

## Inputs

client/product可选（未传与空串区分）；status可选draft/active；q可选，deep=0/1，include_deleted=false，page>=1，page_size=1..100默认20。

## Outputs

success/message/total/page/page_size/items。items仅元数据（ID、作用域、名称、别名、描述、状态、revision、创建/更新时间），无文档；page转limit/offset。数据库错误按503/500传播，不伪装空列表。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
