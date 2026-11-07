# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.web_search_data

## Signature

`SearchDataInterface.web_search_data(self, query: str, client: str=None, index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, page_size: int=None, page_num: int=1, score_threshold: float=None) -> List[Dict[str, Any]]`

## Inputs

旧版 `query/client/index_names/condition_dicts/page_size/page_num/score_threshold`。

## Outputs

返回 `(candidate_docs, total_num)`；保留类目名称转 ID、默认 page_size=10000、多模态 URL
渲染和 `score=min(score/5, 1)`。
index_names 接受逗号分隔字符串或列表；类目名映射可用注入的 category_client，
未注入则复用现有通用 map_cate_name_to_id。

## SQL

无；读 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
