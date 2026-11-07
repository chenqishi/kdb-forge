# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.update_data_value

## Signature

`SearchDataInterface.update_data_value(self, index_name: str, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> bool`

## Inputs

索引、更新字段字典、AND 条件列表。

## Outputs

批量更新是否成功。

## SQL

无；写 Elasticsearch update_by_query。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
