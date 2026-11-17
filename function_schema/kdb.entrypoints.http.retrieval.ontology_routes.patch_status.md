# kdb.entrypoints.http.retrieval.ontology_routes.patch_status

## Signature

`patch_status(ontology_id: OntologyID, body: PatchStatusRequest, service: OntologyService=Depends(get_service))`

## Inputs

路径ontology_id；body.status仅draft/active，revision为正整数。 service经Depends(get_service)注入。

## Outputs

200：meta，revision+1（同状态也增加），不重写文档。状态非法400；UPDATE=0时probe，不存在/软删404，否则409/current_revision。 路由仅传参/返回，文档业务规则交service；HTTP参数验证失败400 ONTOLOGY_BAD_REQUEST。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
