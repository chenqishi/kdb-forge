# tests.services.test_extracted_business_adapters.test_language_rule_precedes_unchanged_model_fallback

## Signature

`test_language_rule_precedes_unchanged_model_fallback(monkeypatch, rule)`

## Inputs

合成数据、临时目录与 pytest 替身；不访问线上服务。

## Outputs

规则优先；规则未命中才调用原模型 predict(text,k=1)，标签和置信度保持原格式。

## SQL

无直接 SQL；外部依赖在测试中由替身隔离。

## Source

`tests/services/test_extracted_business_adapters.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
