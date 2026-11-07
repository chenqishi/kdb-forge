# kdb.mining.crawlers.web_crawl.web_batch_crawler.process_crawled_content_json_format

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

`src/kdb/mining/crawlers/web_crawl/web_batch_crawler.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
