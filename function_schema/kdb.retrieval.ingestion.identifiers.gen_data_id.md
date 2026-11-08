# kdb.retrieval.ingestion.identifiers.gen_data_id

## Signature

`gen_data_id(data: Dict[str, Any]) -> str`

## Description

生成知识记录的 _id：对 `f"{title}_{content}_{data_type}"` 进行 UTF-8 编码后计算 MD5。当前实现直接计算，不依赖旧路径或回退实现。`process_one_data` 仅在记录缺少 `_id` 时调用；已有 `_id` 保留。与磁盘数据集读取器的 `gen_local_dataset_record_id` 不同，后者对整个记录的排序 JSON 计算 MD5。

## Inputs

- `data` (Dict): 含 `title` / `content` / `data_type`（缺失按空串）。

## Outputs

- `str`：32 位十六进制 MD5。

## 关键依赖

- Python 标准库 `hashlib`。

## SQL

无。

## Source

`src/kdb/retrieval/ingestion/identifiers.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
