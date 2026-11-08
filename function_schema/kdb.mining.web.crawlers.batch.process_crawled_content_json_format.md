# kdb.mining.web.crawlers.batch.process_crawled_content_json_format

## Signature

`process_crawled_content_json_format(input_file, output_dir, flag='')`

## Inputs

- `input_file: str`: JSONL crawl manifest.
- `output_dir: str`: output directory.
- `flag: str = ''`: task identifier used in output naming.

## Outputs

- TSV processing manifest path. Static HTML extraction does not create a browser driver.

## SQL

None.

## Source

`src/kdb/mining/web/crawlers/batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
