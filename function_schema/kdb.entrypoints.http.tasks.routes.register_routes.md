# kdb.entrypoints.http.tasks.routes.register_routes

## Signature

`register_routes(app)`

## Inputs

The single existing application, constructed by its entrypoint.

## Outputs

Registers the unchanged path/method/response declarations and handlers once. Does not construct an app, initialize clients, start threads, or issue SQL.

## SQL

None; handler SQL contracts remain unchanged.

## Source

`src/kdb/entrypoints/http/tasks/routes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
