# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.batch_insert_data

## Signature

`SearchDataInterface.batch_insert_data(self, data_list: List[Dict[str, Any]], check_duplicate: bool=True) -> List[bool]`

## Inputs

旧版 `data_list` 和 `check_duplicate`。

## Outputs

按旧顺序返回每条 `insert_data` 的结果列表。

## SQL

无；写 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
