# tests.mining.test_html_text_only_pipeline.test_text_only_stages_read_firecrawl_content_when_untranslated

## Signature

`test_text_only_stages_read_firecrawl_content_when_untranslated(tmp_path, monkeypatch)`

## Inputs

- Pytest temporary directory and monkeypatch fixture.

## Outputs

Regression assertions that translation reads `firecrawl_content`, and untranslated QA and segment stages do the same in text-only mode.

## SQL

None.

## Source

`tests/mining/test_html_text_only_pipeline.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
