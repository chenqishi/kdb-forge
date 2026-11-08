# kdb.retrieval.search.multi_query.search_data_by_multi_query

## Signature

`search_data_by_multi_query(self, query_list: List[str], index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, size: int=10, search_type: str='qa', data_type: str='text', use_synonyms=False) -> Tuple[List[Dict[str, Any]], int]`

## Inputs

旧版多 query 参数：`query_list`、`index_names`、`condition_dicts`、`size`、检索类型和同义词开关。

## Outputs

返回 `(candidate_docs, total_num)`，保留多 query 合并和异常线程回退。
index_names 同时接受字符串和列表；保留本地最新多模态 URL 渲染。

## SQL

无；读 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.search_data_by_multi_query`

## Source

`src/kdb/retrieval/search/multi_query.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
