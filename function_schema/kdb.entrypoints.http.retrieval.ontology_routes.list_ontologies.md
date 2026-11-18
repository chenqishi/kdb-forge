# kdb.entrypoints.http.retrieval.ontology_routes.list_ontologies

## Signature

`list_ontologies(client: ScopeQuery=None, product: ScopeQuery=None, status: Optional[OntologyStatus]=None, q: Optional[str]=None, deep: Annotated[int, Query(ge=0, le=1)]=0, include_deleted: bool=False, audit_status: Annotated[AuditFilter, Query(description='默认仅审核通过；all不过滤审核状态，软删筛选独立')]='approved', page: Annotated[int, Query(description='页码，从1开始，范围由业务服务校验')]=1, page_size: Annotated[int, Query(description='每页条数，1至100，范围由业务服务校验')]=schema.DEFAULT_PAGE_SIZE, service: OntologyService=Depends(get_service))`

## Inputs

client/product可选，未传不过滤、空串只取公用；status可选active/inactive。audit_status默认approved，可传pending/rejected/all；include_deleted=false；q可选、deep=0/1；page>=1，page_size=1..100默认100。所有HTTP筛选和分页位于query。 service经Depends(get_service)注入。

## Outputs

success/message/total/page/page_size/items。列表项包含两个状态与元数据，不加载文档。默认未删且approved，status缺省不过滤；all在service转为仓储None。COUNT与分页使用相同条件。分页类型/范围由service统一校验，失败400/请求参数不合法；数据库故障不能伪装成空列表。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
