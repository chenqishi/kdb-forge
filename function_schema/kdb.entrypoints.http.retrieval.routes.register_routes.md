# kdb.entrypoints.http.retrieval.routes.register_routes

## Signature

`register_routes(app)`

## Inputs

The single existing application, constructed by its entrypoint.

## Outputs

Registers the unchanged twelve original path/method/response declarations and handlers once, then the eight ontology operations using register_ontology_routes(app). Ontology request errors are scoped to /ontology; other paths retain their original validation handler. Does not construct an app, initialize clients, start threads, or issue SQL.

## SQL

None; handler SQL contracts remain unchanged.

## Source

`src/kdb/entrypoints/http/retrieval/routes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
