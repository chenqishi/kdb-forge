# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.resolve_file_name

## Signature

`SearchDataInterface.resolve_file_name(self, index_name: str, name: str, match_mode: str='exact') -> Dict[str, Any]`

## Inputs

索引、输入文件名、exact/fuzzy match_mode。

## Outputs

旧 `{matched, matched_name, doc_count, dice, reason}` 结构。

## SQL

无；读 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
