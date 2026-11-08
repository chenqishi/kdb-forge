# kdb.mining.web.crawlers.batch.run_crawl_task_info

## Signature

`run_crawl_task_info(task_id, task_info, output_file)`

## Inputs

- `task_id: str`
- `task_info: dict | JSON str`: existing URL task payload. Optional top-level `firecrawl_only` enables browser-free explicit URL crawling and requires `is_use_firecrawl=true` plus depth 1 for every URL.
- `output_file: str`

## Outputs

- JSONL crawl manifest at `output_file`; returns that path.

## SQL

None. Task persistence is owned by the control service.

## Source

`src/kdb/mining/web/crawlers/batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
