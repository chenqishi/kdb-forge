# run_crawl_task_info

## Inputs

- `task_id: str`
- `task_info: dict | JSON str`: existing URL task payload. Optional top-level `firecrawl_only` enables browser-free explicit URL crawling and requires `is_use_firecrawl=true` plus depth 1 for every URL.
- `output_file: str`

## Outputs

- JSONL crawl manifest at `output_file`; returns that path.

## SQL

None. Task persistence is owned by the control service.
