# WebBatchCrawler.process_crawl_url

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
