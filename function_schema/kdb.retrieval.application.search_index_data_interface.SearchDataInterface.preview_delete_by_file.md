# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.preview_delete_by_file

## Signature

`SearchDataInterface.preview_delete_by_file(self, index_name: str, file_names: List[str], match_mode: str='exact', data_types: Optional[List[str]]=None, audit_results: Optional[List[int]]=None, sample_size: int=10) -> Dict[str, Any]`

## Inputs

旧索引、文件名列表、匹配模式、类型/审核过滤和 sample_size。

## Outputs

旧预览结构；不修改 ES。

## SQL

无；读取 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
