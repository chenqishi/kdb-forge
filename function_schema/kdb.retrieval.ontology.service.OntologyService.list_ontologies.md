# kdb.retrieval.ontology.service.OntologyService.list_ontologies

## Signature

`OntologyService.list_ontologies(self, client=None, product=None, status=None, q=None, deep=False, include_deleted=False, page=1, page_size=DEFAULT_PAGE_SIZE, audit_status='approved') -> dict`

## Inputs

client/product可选，未传不过滤、空串只取公用；status可选active/inactive。audit_status默认approved，可传pending/rejected/all；include_deleted=false；q可选、deep=0/1；page>=1，page_size=1..100默认100。所有HTTP筛选和分页位于query。

## Outputs

success/message/total/page/page_size/items。列表项包含两个状态与元数据，不加载文档。默认未删且approved，status缺省不过滤；all在service转为仓储None。COUNT与分页使用相同条件。分页类型/范围由service统一校验，失败400/请求参数不合法；数据库故障不能伪装成空列表。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
