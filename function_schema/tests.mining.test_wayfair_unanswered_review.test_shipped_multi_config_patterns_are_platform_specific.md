# tests.mining.test_wayfair_unanswered_review.test_shipped_multi_config_patterns_are_platform_specific

## Signature

`test_shipped_multi_config_patterns_are_platform_specific()`

## Inputs

当前平台分组配置与合成回复文本。

## Outputs

断言Wayfair/Mercado各自配置命中本平台样例且不串用另一平台规则。

## SQL

无；纯本地回归。

## Source

`tests/mining/test_wayfair_unanswered_review.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
