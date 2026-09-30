# test_dual_native_retrieval_routes_and_deduplicates

## Inputs
es8_stack, single/multiple query service methods, same document ID in two providers.

## Outputs
Separate BM25/native nested KNN requests, shared filters, routed hosts, per-index dedup, similarity and multimodal URL postprocessing.

## SQL
None; offline only.
