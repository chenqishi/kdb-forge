# kdb.retrieval.file_operations.preview_delete_by_file

## Signature

`preview_delete_by_file(self, index_name: str, file_names: List[str], match_mode: str='exact', data_types: Optional[List[str]]=None, audit_results: Optional[List[int]]=None, sample_size: int=10) -> Dict[str, Any]`

## Inputs

旧索引、文件名列表、匹配模式、类型/审核过滤和 sample_size。

## Outputs

旧预览结构；不修改 ES。

## SQL

无；读取 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.preview_delete_by_file`

## Source

`src/kdb/retrieval/file_operations.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
