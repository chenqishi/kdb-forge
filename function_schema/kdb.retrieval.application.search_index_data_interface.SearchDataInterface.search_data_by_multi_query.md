# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.search_data_by_multi_query

## Signature

`SearchDataInterface.search_data_by_multi_query(self, query_list: List[str], index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, size: int=10, search_type: str='qa', data_type: str='text', use_synonyms=False) -> Tuple[List[Dict[str, Any]], int]`

## Inputs

旧版多 query 参数：`query_list`、`index_names`、`condition_dicts`、`size`、检索类型和同义词开关。

## Outputs

返回 `(candidate_docs, total_num)`，保留多 query 合并和异常线程回退。
index_names 同时接受字符串和列表；保留本地最新多模态 URL 渲染。

## SQL

无；读 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
