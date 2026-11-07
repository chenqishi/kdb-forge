# kdb.mining.crawlers.web_crawl.web_batch_crawler.WebBatchCrawler.process_crawl_url

## Signature

`WebBatchCrawler.process_crawl_url(self, url, platform, content_type, crawler_degree, keywords, keep_attr_name=None, current_depth=1, limit_page_numbs=None, use_firecrawl=False, firecrawl_only=False)`

## Inputs

- Existing crawl inputs: URL, platform, content type, depth, keywords, optional filename/query and page limits.
- `use_firecrawl: bool = False`: fetch Firecrawl body text.
- `firecrawl_only: bool = False`: for explicit depth-1 URLs, use Firecrawl as the authoritative body and do not use Selenium.

## Outputs

- List of crawl-result dictionaries with local HTML path and, when enabled, Firecrawl text path.
- In `firecrawl_only` mode, empty Firecrawl content fails that URL and is not emitted as a successful result.

## Constraints

- `firecrawl_only` requires `use_firecrawl=True` and `crawler_degree=1`; this prevents silently losing recursive link discovery.

## SQL

None.

## Source

`src/kdb/mining/crawlers/web_crawl/web_batch_crawler.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
