# kdb.entrypoints.http.retrieval.ontology_routes.register_ontology_routes

## Signature

`register_ontology_routes(app)`

## Inputs

既有retrieval FastAPI app，每个应用启动注册一次。

## Outputs

注册8条动词式路径：POST /insert_ontology、/get_ontology、/list_ontologies、/update_ontology、/update_ontology_status、/delete_ontology、/select_ontology，GET /ontology_meta；insert为201，其余成功200。注册OntologyError/RequestValidationError处理器，按request.scope中的route.tags是否包含ontology判定扁平错误信封，与URL或代理前缀无关；其他路径委托原同步/异步处理器或默认detail形态。不启动服务，不初始化连接，不改变原12条路由。

## SQL

无直接 SQL，经 service → repository；复用 dops_ontology 与共享 MySQL 连接池。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_routes.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
