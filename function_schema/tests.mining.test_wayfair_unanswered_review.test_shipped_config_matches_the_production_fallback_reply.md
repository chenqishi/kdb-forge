# tests.mining.test_wayfair_unanswered_review.test_shipped_config_matches_the_production_fallback_reply

## Signature

`test_shipped_config_matches_the_production_fallback_reply()`

## Inputs

当前合成配置与已发货fallback回复样本。

## Outputs

断言fallback模式被正确识别，样例联系人使用support@example.invalid；不触发真实平台、客户或消息请求。

## SQL

无；纯本地回归。

## Source

`tests/mining/test_wayfair_unanswered_review.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
