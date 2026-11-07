# WebBatchCrawler.fetch_html_without_browser

## Inputs

- `url: str`: page URL.
- Instance `auth_config`; optional cookie, user-agent, referer, headers, and `http_timeout` (default 30 seconds).

## Outputs

- HTML response text obtained with an HTTP GET and a finite timeout.
- Raises for network and non-success HTTP errors.

## SQL

None.
