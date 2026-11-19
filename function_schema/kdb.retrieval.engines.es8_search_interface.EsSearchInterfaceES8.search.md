# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.search

## Signature

`EsSearchInterfaceES8.search(self, query: Optional[Dict[str, Any]]=None, size: int=10, index_names: IndexNames=None) -> List[Dict[str, Any]]`

## Inputs

query、size、目标索引。

## Outputs

旧单路检索结果列表。native KNN 的 k 随请求 size 增长，确保离线Top60不被默认k=10截断；size=None使用10条，size=0仍保留空返回语义。不设置min_score，不增加审核/platform过滤。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
