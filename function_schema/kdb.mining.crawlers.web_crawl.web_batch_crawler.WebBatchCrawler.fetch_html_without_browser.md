# kdb.mining.crawlers.web_crawl.web_batch_crawler.WebBatchCrawler.fetch_html_without_browser

## Signature

`WebBatchCrawler.fetch_html_without_browser(self, url)`

## Inputs

- `url: str`: page URL.
- Instance `auth_config`; optional cookie, user-agent, referer, headers, and `http_timeout` (default 30 seconds).

## Outputs

- HTML response text obtained with an HTTP GET and a finite timeout.
- Raises for network and non-success HTTP errors.

## SQL

None.

## Source

`src/kdb/mining/crawlers/web_crawl/web_batch_crawler.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
