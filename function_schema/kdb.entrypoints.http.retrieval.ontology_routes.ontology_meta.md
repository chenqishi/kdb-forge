# kdb.entrypoints.http.retrieval.ontology_routes.ontology_meta

## Signature

`ontology_meta()`

## Inputs

无入参、无service依赖。

## Outputs

200 success/message，加schema_version、status_values、scope_values、data_types、item_types、cardinalities、severities、reserved_fields、limits；限制值与schema/model一致，不连接数据库。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
