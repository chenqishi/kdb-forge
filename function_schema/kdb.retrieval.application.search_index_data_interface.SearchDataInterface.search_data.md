# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.search_data

## Signature

`SearchDataInterface.search_data(self, query: Dict[str, Any], size: Optional[int]=None, index_names: Optional[Union[str, List[str]]]=None) -> List[Dict[str, Any]]`

## Inputs

旧版 `search_data(query, size=None, index_names=None)`。

## Outputs

返回文档列表，保留旧通用 query 结构。

## SQL

无；读 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
