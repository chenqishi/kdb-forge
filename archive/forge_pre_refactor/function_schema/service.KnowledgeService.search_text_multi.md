# KnowledgeService.search_text_multi

## Inputs
query_list, index_name (comma-separated string/list), condition_dicts, size,
search_type, data_type, use_synonyms.
## Outputs
(docs, total), delegate to search_data_by_multi_query without duplicating retrieval.
Keep local latest multimodal URL rendering; ES traffic stays on the routed engine.
## SQL
None; Elasticsearch read via compatibility layer.
