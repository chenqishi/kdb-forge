# kdb.entrypoints.http.retrieval.ontology_routes.update_ontology_status

## Signature

`update_ontology_status(body: UpdateOntologyStatusRequest, service: OntologyService=Depends(get_service))`

## Inputs

body.ontology_id、正整数revision；status=active/inactive必填。保留原有启停入口，不接收review_status；审核使用update_ontology。 service经Depends(get_service)注入。

## Outputs

200：meta含两个状态，单次成功revision+1（相同值也增加），不重写文档。仅更新启停，委托update_ontology复用版本和错误处理；文档及审核结果保持不变。审核字段或非法/缺失status返回400；不存在或已删404，版本冲突409/current_revision。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
