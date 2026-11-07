# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.delete_data

## Signature

`SearchDataInterface.delete_data(self, data_id: str, index_names: Optional[Union[str, List[str]]]=None, refresh: bool=False) -> bool`

## Inputs

旧 `data_id, index_names=None, refresh=False`。

## Outputs

删除是否成功。

## SQL

无；写 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
