# kdb.retrieval.categories.mapping.map_cate_name_to_id

## Signature

`map_cate_name_to_id(self, client, category_name)`

## Inputs

client、类目全路径名称。

## Outputs

叶子 category ID 或 None。

## SQL

无。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.map_cate_name_to_id`

## Source

`src/kdb/retrieval/categories/mapping.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
