# RoutedLegacyEngine.count_by_query

## Inputs
Original forge `index_name, query, require_complete=False`. Native DSL is passed through unchanged.

## Outputs
For ordinary count, delegate directly to published ES8 method. For forge strict count only, retain original SDK flags ignore_unavailable=False, allow_no_indices=False, expand_wildcards="none", then use the published complete_count validator. No new query construction or retrieval algorithm. Same provider binding as published engine.

## SQL
None. Only native Elasticsearch count request; no ensure/index writes.
