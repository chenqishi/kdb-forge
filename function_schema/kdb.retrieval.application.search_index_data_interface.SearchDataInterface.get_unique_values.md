# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.get_unique_values

## Signature

`SearchDataInterface.get_unique_values(self, index_name: str, field_name: str, size: int=10000, include_doc_count: bool=False, extra_query: Optional[Dict[str, Any]]=None) -> Union[List[str], List[Dict[str, Any]]]`

## Inputs

旧 index_name、field_name、size、include_doc_count、extra_query。

## Outputs

唯一值列表或带计数的字典列表。

## SQL

无；读 Elasticsearch terms aggregation。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
