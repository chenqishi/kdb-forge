# kdb.services.forge_compat.adapter.KnowledgeService.search_text_multi

## Signature

`KnowledgeService.search_text_multi(self, query_list: List[str], index_name=None, condition_dicts=None, size: int=10, search_type: str='qa', data_type: str='text', use_synonyms: bool=False) -> Tuple[List[Dict[str, Any]], int]`

## Inputs

`self, query_list: List[str], index_name=None, condition_dicts=None, size: int=10, search_type: str='qa', data_type: str='text', use_synonyms: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

query_list, index_name (comma-separated string/list), condition_dicts, size,
search_type, data_type, use_synonyms.

## Outputs

Thin protocol forwarding to the single published implementation; preserves normal return values and exceptions.

(docs, total), delegate to search_data_by_multi_query without duplicating retrieval.
Keep local latest multimodal URL rendering; ES traffic stays on the routed engine.

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

None; Elasticsearch read via compatibility layer.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
