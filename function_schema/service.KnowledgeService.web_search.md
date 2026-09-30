# KnowledgeService.web_search

## Inputs
query, client, index_name (string/list), condition_dicts, page_size, page_num,
score_threshold.
## Outputs
Delegate to web_search_data: generic explicit category filters, pagination, score
normalization and multimodal rendering. No mining-specific inference.
## SQL
None; Elasticsearch/category HTTP reads only.
