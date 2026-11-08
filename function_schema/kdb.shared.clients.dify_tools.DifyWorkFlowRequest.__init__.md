# kdb.shared.clients.dify_tools.DifyWorkFlowRequest.__init__

## Signature

`__init__(self, api_base=None, api_key=None, max_retries=3, system_prompt=None, timeout=600)`

## Description

初始化 Dify workflow blocking API 客户端。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| api_base | str\|None | 否 | Dify API base URL |
| api_key | str\|None | 否 | Dify workflow API key |
| max_retries | int | 否 | 最大重试次数，默认 3 |
| system_prompt | str\|None | 否 | 可选 system prompt，会合并到 inputs |
| timeout | int\|float | 否 | 单次 HTTP blocking 请求超时秒数，默认 600 |

## Outputs

| 类型 | 说明 |
|------|------|
| None | 初始化实例属性 |

## SQL

No SQL access.

## Source

`src/kdb/shared/clients/dify_tools.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
