# kdb.mining.common.context.html.load_html_business_context

## Signature

`load_html_business_context(business_context_path)`

## Description

读取 `business_context_builder` 产出的业务上下文 JSON。未传路径、未启用或读取失败时返回 None。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| business_context_path | str\|None | 否 | `business_context.json` 路径 |

## Outputs

| 类型 | 说明 |
|------|------|
| dict\|None | 可用业务上下文，必须包含 `enabled=true` 和 `context_text` |

## SQL

不读写 SQL。

## Source

`src/kdb/mining/common/context/html.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
