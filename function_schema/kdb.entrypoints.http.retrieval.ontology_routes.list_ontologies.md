# kdb.entrypoints.http.retrieval.ontology_routes.list_ontologies

## Signature

`list_ontologies(client: ScopeQuery=None, product: ScopeQuery=None, status: Optional[Literal['draft', 'active']]=None, q: Optional[str]=None, deep: Annotated[int, Query(ge=0, le=1)]=0, include_deleted: bool=False, page: Annotated[int, Query(ge=1)]=1, page_size: Annotated[int, Query(ge=1, le=100)]=20, service: OntologyService=Depends(get_service))`

## Inputs

client/product可选（未传与空串区分）；status可选draft/active；q可选，deep=0/1，include_deleted=false，page>=1，page_size=1..100默认20。 service经Depends(get_service)注入。

## Outputs

success/message/total/page/page_size/items。items仅元数据（ID、作用域、名称、别名、描述、状态、revision、创建/更新时间），无文档；page转limit/offset。数据库错误按503/500传播，不伪装空列表。 路由仅传参/返回，文档业务规则交service；HTTP参数验证失败400 ONTOLOGY_BAD_REQUEST。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
