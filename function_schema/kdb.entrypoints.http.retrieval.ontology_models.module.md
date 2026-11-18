# kdb.entrypoints.http.retrieval.ontology_models.module

## Signature

`kdb.entrypoints.http.retrieval.ontology_models (module)`

## Inputs

按设计 v8 对应文档模型、请求模型或模块参数；Python 3.9 / Pydantic v2。

## Outputs

创建默认status=active、audit_status=pending（未审核）；统一更新请求data_json/status/audit_status均可选（至少更新一项）；独立启停请求只接受必填status。所有元数据、完整/大纲/选取及document响应均暴露audit_status；详情和列表默认approved，可用all查看所有审核状态。

Pydantic v2 strict/extra=forbid模型，描述文档或HTTP请求/响应的字段、默认值、长度、类型和Literal枚举；不执行IO。文档的跨节点唯一性/引用校验交validation；HTTP请求错误交按ontology tag作用的400处理器。Get/Update/UpdateStatus/Delete请求的ontology_id为body内32位小写hex；Delete的revision也是body字段。创建回OntologyMeta；详情采用OntologyFull/OntologyOutline联合类型；列表采用OntologyListItem；选取采用SelectedOntologyDocument/OntologyOutline联合类型并保留原字段集合。

## SQL

无直接 SQL。

## Source

`src/kdb/entrypoints/http/retrieval/ontology_models.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
