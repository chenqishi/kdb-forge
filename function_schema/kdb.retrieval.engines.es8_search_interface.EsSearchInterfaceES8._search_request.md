# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._search_request

## Signature

`EsSearchInterfaceES8._search_request(self, client: Any, indexes: Sequence[str], query: Dict[str, Any], size: int, from_: int=0, min_score: Optional[float]=None, sort: Optional[Sequence[Any]]=None, search_after: Optional[Sequence[Any]]=None, scroll: Optional[str]=None, source_includes: Optional[Sequence[str]]=None, source_excludes: Optional[Sequence[str]]=None, aggs: Optional[Dict[str, Any]]=None, track_total_hits: Optional[Union[bool, int]]=None, source: Optional[Union[bool, Mapping[str, Any]]]=None, pit: Optional[Mapping[str, Any]]=None, seq_no_primary_term: bool=False, stored_fields: Optional[Sequence[str]]=None) -> Dict[str, Any]`

## Description

Inputs: unchanged original client/indexes/query/size/from/min_score/sort/search_after/scroll/source_includes/excludes/aggs parameters; add optional track_total_hits, source, PIT, seq_no_primary_term and stored_fields metadata for conditional updates. Existing calls retain exact request semantics. Outputs: original strict-shard response; PIT omits index, response pit_id updates retries and caller dictionary including partial/last empty page, facilitating latest context cleanup. Three retries unchanged. No SQL or write side effects.

## Inputs

ES client、index 列表、query DSL、size、可选 from_/sort/search_after/scroll/source_includes/source_excludes。

## Outputs

ES8 search response。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
