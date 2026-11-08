# kdb.mining.common.ingestion.deleted_sources.split_by_source_status

## Signature

`split_by_source_status(input_file, output_keep=None, output_skip=None, field_num=0, index_name='wayfair', es_config='config/config_es_engine.json', output_dir='output/skip_deleted_sources', name_field_num=None)`

## Purpose

把待入库文件按来源文章的下架状态拆成「可插入」和「跳过」两份，并出对照报告。
入库前的固定闸门，避免把知识重新灌回已经人工下架的文章。

## Inputs

- `input_file` (str): 待入库文件，每行一个 JSON。
- `output_keep` / `output_skip` (str|None): 输出路径，默认在 `input_file` 同目录加 `.keep` / `.skipped` 后缀。
- `field_num` (int): JSON 所在的制表符字段位，默认 0（整行就是 JSON 时用 0）。
- `name_field_num` (int|None): 第几列**直接就是文件名**（不是 JSON）。给了它就不再解析 JSON，
  用于阶段间的映射清单——例如 QA 的 `qa_regen_*.txt`，第 1 列是 `from_file_name`。
  QA 产物按文件散在各解析目录里，没有逐条 JSON 可拆，闸门只能卡在映射清单这一层。
- `index_name` (str): ES 索引，默认 `wayfair`。
- `es_config` (str): ES 连接配置路径。
- `output_dir` (str): 报告目录。

来源文件名的读取顺序：`ext_info.from_file_name` → `from_file_name`，
两种产物（segment_knowledge 与 search_data）都能直接用。

## Outputs

- `str`: 报告 JSON 路径，含各 verdict 的文件名单与行数统计。

副作用：写出 `output_keep` 与 `output_skip` 两个文件。不改 ES。

## SQL

No SQL access.

## Source

`src/kdb/mining/common/ingestion/deleted_sources.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
