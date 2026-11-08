# kdb.mining.chat.query_analysis.ecommerce._questionize

## Signature

`_questionize(text: str, platform: str) -> str`

## Description

把候选文本规范成中文问句，修正 `入住` 为 `入驻`，必要时补充平台范围和问号。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 候选文本 |
| platform | str | 是 | 平台范围 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 规范问句；输入无效时返回空字符串 |

## SQL

无 SQL。

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
