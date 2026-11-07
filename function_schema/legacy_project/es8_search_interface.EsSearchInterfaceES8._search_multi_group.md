# es8_search_interface.EsSearchInterfaceES8._search_multi_group

## Inputs / Outputs
Inputs: one validated provider binding, ordered exact index names, query, size, mode. Build independent BM25/native KNN bodies for each index with unchanged per-route budgets and filter/source.
Outputs: native msearch batches (max_concurrent_searches=2) for multiple routes; single route still uses search. Merge in original index/route order, preserve total calculation and first-score rule. For old default dual with vector, request-only excludes indexes.embedding/image_indexes.embedding, retaining title/content root vectors/text/metadata; vector inner_hits restores matched nested vectors, BM25-only retains old root-vector fallback. Text-only/nondual returns full source. Native batch and independent fallback use identical source exclusions; filters/budgets/order/query and CRUD/storage remain unchanged. Per-item error logged/skipped; successful routes and final partial-shard hits retained. Query construction/mapping errors remain observable; no maintenance changes.

## SQL
None.
