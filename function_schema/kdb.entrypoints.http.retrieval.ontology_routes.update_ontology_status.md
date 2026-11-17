# kdb.entrypoints.http.retrieval.ontology_routes.update_ontology_status

## Signature

`update_ontology_status(body: UpdateOntologyStatusRequest, service: OntologyService = Depends(get_service))`

## Inputs

body.ontology_id为32位小写hex；body.status仅draft/active，revision为正整数。 service经Depends(get_service)注入。

## Outputs

200：meta，revision+1（同状态也增加），不重写文档。状态非法400；UPDATE=0时按ID回查，不存在/软删404，否则409/current_revision。 路由仅传参/返回，文档业务规则交service；HTTP参数验证失败400 ONTOLOGY_BAD_REQUEST。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
