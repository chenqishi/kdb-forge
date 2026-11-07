# EsSearchInterfaceES8._search_request

Inputs: unchanged original client/indexes/query/size/from/min_score/sort/search_after/scroll/source_includes/excludes/aggs parameters; add optional track_total_hits, source, PIT, seq_no_primary_term and stored_fields metadata for conditional updates. Existing calls retain exact request semantics. Outputs: original strict-shard response; PIT omits index, response pit_id updates retries and caller dictionary including partial/last empty page, facilitating latest context cleanup. Three retries unchanged. No SQL or write side effects.
