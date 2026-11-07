# es8_search_interface.EsSearchInterfaceES8._msearch_with_shard_check

## Inputs / Outputs
Inputs: alternating mapping headers/bodies with exact original indexes. Reject odd lists, invalid bodies and a single header spanning different providers.
Outputs: native batches per consecutive provider, original response order. Uses bounded native concurrency (2). Subsearches retain all original parameters and full source. Raises invalid routing/mapping and batch transport failures. Online search_multi separately provides visible independent-search fallback; this body helper preserves parameters by native execution.

## SQL
None.
