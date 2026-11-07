# kdb.mining.crawlers.web_crawl.web_batch_crawler.WebBatchCrawler.__init__

## Signature

`WebBatchCrawler.__init__(self, output_dir, auth_config=None, browser_enabled=True)`

## Inputs

- `output_dir: str`: crawler output directory.
- `auth_config: dict | None`: optional cookie, user-agent, headers, referer, and timeout settings.
- `browser_enabled: bool = True`: whether to create a Selenium driver.

## Outputs

- Initializes crawler state. `driver` is `None` when browser rendering is disabled.

## SQL

None.

## Source

`src/kdb/mining/crawlers/web_crawl/web_batch_crawler.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
