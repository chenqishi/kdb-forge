# kdb.retrieval.ingestion.raw_records.gen_local_dataset_record_id

## Signature

`gen_local_dataset_record_id(data: Dict[str, Any]) -> str`

## Description

为磁盘上的本地数据集记录生成内容 ID。由原 `rawdata_interface.gen_data_id` 更名，算法保持不变：`hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()`。

此 ID 使用整个记录，不是知识入库时基于 `title/content/data_type` 的 ID。正式批量入库通过 `read_data(is_need_id=False)` 关闭读取阶段补 ID；当前默认开启的仓库调用位于手工辅助函数 `test_insert_letian_excel`，未找到调用该辅助函数的正式入口。

## Inputs

- `data`：可由 `json.dumps` 序列化的数据字典。所有字段参与计算，JSON 序列化参数沿用默认值，仅设置 `sort_keys=True`。

## Outputs

- 32 位十六进制 MD5 字符串；不修改输入字典。
- 无法序列化时保留原异常，不新增容错。

## SQL

无。无网络、文件写入或数据库操作。

## Source

`src/kdb/retrieval/ingestion/raw_records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
