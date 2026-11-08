# tests.mining.test_web_batch_crawler_firecrawl_only.test_run_task_firecrawl_only_validates_depth_and_writes_manifest

## Signature

`test_run_task_firecrawl_only_validates_depth_and_writes_manifest(tmp_path, monkeypatch)`

## Inputs

- Pytest temporary directory and monkeypatch fixture.

## Outputs

- Regression assertions for task manifest output, no Selenium startup, and rejection of recursive depth.

## SQL

None.

## Source

`tests/mining/test_web_batch_crawler_firecrawl_only.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
