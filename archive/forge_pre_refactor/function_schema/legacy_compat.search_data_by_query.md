# LegacySearchDataInterfaceMixin.search_data_by_query

## Inputs
旧版 query、index_names、condition_dicts、size、search_type、data_type、use_synonyms。

## Outputs
返回 `(candidate_docs, total_num)`，保留候选预算、similarity 计算和多模态 URL 渲染。

## SQL
无；读 Elasticsearch。
