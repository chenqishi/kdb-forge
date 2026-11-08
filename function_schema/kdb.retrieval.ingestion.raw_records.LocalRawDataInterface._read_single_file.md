# kdb.retrieval.ingestion.raw_records.LocalRawDataInterface._read_single_file

## Signature

`_read_single_file(self, file_path: str, is_need_id: bool=True) -> Iterator[Dict[str, Any]]`

## Inputs

- `file_path`：UTF-8 本地数据文件；逐行取去除首尾空白后的最后一个制表符字段，按 JSON 解析。
- `is_need_id`：默认 `True`；只有记录缺少 `_id` 且此开关开启时，调用 `gen_local_dataset_record_id` 补充磁盘数据集记录 ID。已有 `_id` 保留。

## Outputs

- 按文件顺序迭代字典记录；非字典 JSON 不输出。
- JSON 解码失败跳过；行内其他异常打印原错误信息并跳过。文件打开失败仍向调用方抛出。
- 正式批量入库由 `read_data(is_need_id=False)` 传递关闭开关，不在读取阶段生成 ID。

## SQL

无。只读取指定本地文件。

## Source

`src/kdb/retrieval/ingestion/raw_records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
