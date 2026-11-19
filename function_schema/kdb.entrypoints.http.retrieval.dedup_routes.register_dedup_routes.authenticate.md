# kdb.entrypoints.http.retrieval.dedup_routes.register_dedup_routes.authenticate

## Signature

`register_dedup_routes.authenticate(request)`

## Inputs

Bearer token映射到服务端admin/leader/indices，拒绝无授权与非法Origin。

## Outputs

显式结构化结果；不把失败当完成。

## SQL / ES

无SQL。经单index检索/去重函数访问ES；服务端配置不可由工具参数覆盖。

## Current behavior

原检索服务可选MCP端点，缺配置或enabled=false不注册；Bearer绑定服务端主体，Origin校验，默认工具不公开。

## Source

`src/kdb/entrypoints/http/retrieval/dedup_routes.py`
