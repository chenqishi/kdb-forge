# kdb.mining.web.crawlers.batch.WebBatchCrawler.__init__

## Signature

`__init__(self, output_dir, auth_config=None, browser_enabled=True)`

## Inputs

- `output_dir: str`: crawler output directory.
- `auth_config: dict | None`: optional cookie, user-agent, headers, referer, and timeout settings.
- `browser_enabled: bool = True`: whether to create a Selenium driver.

## Outputs

- Initializes crawler state. `driver` is `None` when browser rendering is disabled.

## SQL

None.

## Source

`src/kdb/mining/web/crawlers/batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
