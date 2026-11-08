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

`tests/mining/test_wayfair_unanswered_review.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
