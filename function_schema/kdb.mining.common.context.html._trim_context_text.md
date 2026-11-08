# kdb.mining.common.context.html._trim_context_text

## Signature

`_trim_context_text(text, max_chars=4000)`

## Description

限制业务上下文文本长度，避免挤占 HTML 正文的模型输入窗口。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | Any | 否 | 上下文文本 |
| max_chars | int | 否 | 最大字符数，默认 4000 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 截断后的上下文文本 |

## SQL

不读写 SQL。

## Source

`src/kdb/mining/common/context/html.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
