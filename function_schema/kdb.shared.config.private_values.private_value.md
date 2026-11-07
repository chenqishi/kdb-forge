# kdb.shared.config.private_values.private_value

## Signature

`private_value(key: str) -> str`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

private_value(key) -> str：在原字面量求值位置读取私有默认值，首次从本项目private/runtime_config/hardcoded_defaults.json加载并缓存。
有效值与私有快照逐项对照；不访问线上、不更换/轮换凭据。私有文件缺失/缺字段会显式失败，不能用空字符串或占位符替代。

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/shared/config/private_values.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
