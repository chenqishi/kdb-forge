# kdb.shared.clients.structured_llm.request_json

## Signature

`request_json(system, payload, config=None, usage=None)`

## Inputs

系统指令、JSON业务数据、显式模型endpoint/api_key/model或现有LLM插件配置；usage为调用方持有累计用量。

## Outputs

返回JSON对象；无模型、调用失败、非法JSON显式异常；累计实际tokens，未知用量单独计数。

## SQL / ES

无数据库访问；模型访问仅按显式配置执行。

## Source

`src/kdb/shared/clients/structured_llm.py`

## Current behavior

直接JSON模型调用或显式本地LLM插件，校验输出对象；成功失败均统计usage，未返回用量记unknown_usage_calls。
