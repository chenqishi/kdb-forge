# kdb.entrypoints.http.retrieval.dedup_routes.register_dedup_routes.mcp

## Signature

`register_dedup_routes.mcp(request: Request)`

## Inputs

JSON-RPC initialize/ping/tools/list/tools/call，工具错误以isError返回；通过线程池执行同步业务，支持sell_agents MCP调用。

## Outputs

显式结构化结果；不把失败当完成。

## SQL / ES

无SQL。经单index检索/去重函数访问ES；服务端配置不可由工具参数覆盖。

## Current behavior

原检索服务可选MCP端点，缺配置或enabled=false不注册；Bearer绑定服务端主体，Origin校验，默认工具不公开。

## Source

`src/kdb/entrypoints/http/retrieval/dedup_routes.py`
