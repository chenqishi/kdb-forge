# kdb.entrypoints.http.retrieval.ontology_routes.create_ontology

## Signature

`create_ontology(body: CreateRequest, service: OntologyService=Depends(get_service))`

## Inputs

完整body.data_json（object或JSON字符串），可选status=draft/active，默认active；禁止在HTTP请求外层传name/client/product等投影字段。 service经Depends(get_service)注入。

## Outputs

201（service返回dict）：success/message/ontology完整视图，含UUID4 hex、revision=1、规范化data_json、document_bytes、投影与时间。先校验status及文档，再事务判重插入、按生成ID回查；同业务键（含draft）409，细节保留已有ID/status/revision。 路由仅传参/返回，文档业务规则交service；HTTP参数验证失败400 ONTOLOGY_BAD_REQUEST。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
