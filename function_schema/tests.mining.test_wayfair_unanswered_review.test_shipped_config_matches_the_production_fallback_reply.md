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

`tests/mining/test_wayfair_unanswered_review.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
