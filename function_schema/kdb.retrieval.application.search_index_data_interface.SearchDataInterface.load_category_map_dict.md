# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.load_category_map_dict

## Signature

`SearchDataInterface.load_category_map_dict(self, client: str, user=None) -> Dict[str, Any]`

## Inputs

`client`、可选 `user`。

## Outputs

缓存类目树并返回旧的成功/空值语义。

## SQL

无；读取配置的类目 HTTP 服务。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
