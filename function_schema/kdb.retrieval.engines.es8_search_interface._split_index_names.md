# kdb.retrieval.engines.es8_search_interface._split_index_names

## Signature

`_split_index_names(index_names: IndexNames, default_index: str) -> List[str]`

## Inputs

单个 index、逗号分隔 index 字符串或 index 列表；默认 index。

## Outputs

小写且去空白的 index 列表；空值抛 `ValueError`。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
