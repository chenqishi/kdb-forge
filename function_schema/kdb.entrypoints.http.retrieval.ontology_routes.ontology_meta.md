# kdb.entrypoints.http.retrieval.ontology_routes.ontology_meta

## Signature

`ontology_meta()`

## Inputs

无入参、无service依赖。

## Outputs

200 success/message，加schema_version、status_values=active/inactive、audit_status_values=pending/approved/rejected、scope_values、各文档枚举、reserved_fields与limits。audit_status是文档保留字段，extensions豁免不变。不初始化或连接数据库。

## SQL

无SQL或数据库依赖。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
