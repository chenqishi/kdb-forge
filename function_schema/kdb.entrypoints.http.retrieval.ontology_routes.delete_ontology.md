# kdb.entrypoints.http.retrieval.ontology_routes.delete_ontology

## Signature

`delete_ontology(ontology_id: OntologyID, revision: Annotated[Optional[int], Query(ge=1)]=None, service: OntologyService=Depends(get_service))`

## Inputs

路径ontology_id；revision可选正整数查询参数。 service经Depends(get_service)注入。

## Outputs

200：deleted=true、ontology meta带del_flag=1；首次删除revision+1；已删再删message=already deleted且revision不变（即使传旧revision）。不存在404；未删且revision不符409/current_revision。 路由仅传参/返回，文档业务规则交service；HTTP参数验证失败400 ONTOLOGY_BAD_REQUEST。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
