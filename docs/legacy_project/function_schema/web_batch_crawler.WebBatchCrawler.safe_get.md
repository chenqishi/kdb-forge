# WebBatchCrawler.safe_get

## Inputs

- `url: str`: page URL.
- `max_retries: int = 3`: maximum browser attempts.

## Outputs

- Browser-rendered page source.
- On a Selenium page-load timeout, stops loading and returns non-empty partial page source; otherwise retries or raises.

## SQL

None.
