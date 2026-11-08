# kdb.retrieval.categories.mapping.get_category_parent_chain

## Signature

`get_category_parent_chain(self, client: str, cate_id: str=None, cate_name: str=None) -> List[Dict[str, Any]]`

## Inputs

client、可选 cate_id/cate_name。

## Outputs

根到叶的类目节点列表。

## SQL

无。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.get_category_parent_chain`

## Source

`src/kdb/retrieval/categories/mapping.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
