# kdb.retrieval.file_operations.resolve_file_name

## Signature

`resolve_file_name(self, index_name: str, name: str, match_mode: str='exact') -> Dict[str, Any]`

## Inputs

索引、输入文件名、exact/fuzzy match_mode。

## Outputs

旧 `{matched, matched_name, doc_count, dice, reason}` 结构。

## SQL

无；读 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.resolve_file_name`

## Source

`src/kdb/retrieval/file_operations.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
