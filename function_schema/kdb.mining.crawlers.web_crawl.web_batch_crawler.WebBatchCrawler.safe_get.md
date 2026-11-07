# kdb.mining.crawlers.web_crawl.web_batch_crawler.WebBatchCrawler.safe_get

## Signature

`WebBatchCrawler.safe_get(self, url, max_retries=3)`

## Inputs

- `url: str`: page URL.
- `max_retries: int = 3`: maximum browser attempts.

## Outputs

- Browser-rendered page source.
- On a Selenium page-load timeout, stops loading and returns non-empty partial page source; otherwise retries or raises.

## SQL

None.

## Source

`src/kdb/mining/crawlers/web_crawl/web_batch_crawler.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
