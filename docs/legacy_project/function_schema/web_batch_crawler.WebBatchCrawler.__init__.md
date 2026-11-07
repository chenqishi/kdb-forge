# WebBatchCrawler.__init__

## Inputs

- `output_dir: str`: crawler output directory.
- `auth_config: dict | None`: optional cookie, user-agent, headers, referer, and timeout settings.
- `browser_enabled: bool = True`: whether to create a Selenium driver.

## Outputs

- Initializes crawler state. `driver` is `None` when browser rendering is disabled.

## SQL

None.
