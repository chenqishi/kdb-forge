# kdb.services.retrieval.app.search

## Signature

`search(request: SearchRequest)`

## Inputs

- `request: SearchRequest`
  - `text`: non-empty query text.
  - `top_k`: maximum number of returned search items.
  - `score_threshold`: optional post-filter threshold on response `score`; values `<= -1` disable filtering.
  - `index_names`: optional comma-separated ES/OpenSearch index names.
  - `condition_dicts`: optional attribute filters passed to the search data interface.
  - `search_type`, `data_type`, `use_synonyms`: ranking and similarity options passed through to the search data interface.

## Outputs

- `SearchResponse.results: List[SearchResult]`
  - Preserves the existing response fields: `q`, `a`, `content`, `score`, `ext_info`, `metadata`, `synonyms_title`.
  - Also exposes the ES document id from each raw result as `id`.
  - Also exposes the dataset from raw `dataset`, falling back to raw `_index` when `dataset` is absent.
  - Also exposes raw `insert_time` and `update_time` when present.
- Error fallback remains `SearchResponse(results=[SearchResult(q="检索结果错误", score=0.0)])`.

## SQL

- No SQL access.
- Reads search results indirectly from `SEARCH_DATA_INTERFACE.search_data_by_query()`, which delegates to ES/OpenSearch.

## Source

`src/kdb/services/retrieval/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
