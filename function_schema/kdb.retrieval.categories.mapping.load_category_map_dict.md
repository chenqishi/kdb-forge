# kdb.retrieval.categories.mapping.load_category_map_dict

## Signature

`load_category_map_dict(self, client: str, user=None) -> Dict[str, Any]`

## Inputs

`client`、可选 `user`。

## Outputs

缓存类目树并返回旧的成功/空值语义。

## SQL

无；读取配置的类目 HTTP 服务。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.load_category_map_dict`

## Source

`src/kdb/retrieval/categories/mapping.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
