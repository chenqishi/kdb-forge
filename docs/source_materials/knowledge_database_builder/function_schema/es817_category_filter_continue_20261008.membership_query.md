# membership_query

Inputs: case and one physical index's mapping. Outputs: independent exact-field filter oracle plus, for nonempty web text only, the legacy BM25 should predicates title^2/content^1.5/indexes.text and synonyms_title boost1.8, minimum_should_match1. Uses no implementation query builder. Exact category matching honors keyword/multi-field mapping. Service tests use threshold<=0 so native count applies without a score threshold. /search count is category membership, not top-K or vector-recall count. SQL: none.
