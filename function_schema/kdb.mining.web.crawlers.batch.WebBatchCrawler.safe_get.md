# kdb.mining.web.crawlers.batch.WebBatchCrawler.safe_get

## Signature

`safe_get(self, url, max_retries=3)`

## Inputs

- `url: str`: page URL.
- `max_retries: int = 3`: maximum browser attempts.

## Outputs

- Browser-rendered page source.
- On a Selenium page-load timeout, stops loading and returns non-empty partial page source; otherwise retries or raises.

## SQL

None.

## Source

`src/kdb/mining/web/crawlers/batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
