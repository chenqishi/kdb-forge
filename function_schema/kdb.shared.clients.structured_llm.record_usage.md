# kdb.shared.clients.structured_llm.record_usage

## Signature

`record_usage(usage, raw)`

## Inputs

累计计数及供应商usage对象。

## Outputs

累计调用数、输入/输出/总tokens及unknown_usage_calls，不把估算冒充实际用量。

## SQL / ES

无数据库访问；模型访问仅按显式配置执行。

## Source

`src/kdb/shared/clients/structured_llm.py`

## Current behavior

直接JSON模型调用或显式本地LLM插件，校验输出对象；成功失败均统计usage，未返回用量记unknown_usage_calls。
