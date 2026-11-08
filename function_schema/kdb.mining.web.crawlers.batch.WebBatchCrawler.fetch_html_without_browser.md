# kdb.mining.web.crawlers.batch.WebBatchCrawler.fetch_html_without_browser

## Signature

`fetch_html_without_browser(self, url)`

## Inputs

- `url: str`: page URL.
- Instance `auth_config`; optional cookie, user-agent, referer, headers, and `http_timeout` (default 30 seconds).

## Outputs

- HTML response text obtained with an HTTP GET and a finite timeout.
- Raises for network and non-success HTTP errors.

## SQL

None.

## Source

`src/kdb/mining/web/crawlers/batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
