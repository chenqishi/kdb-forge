# kdb.mining.query_analysis.ecommerce_query_mining._questionize

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

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
