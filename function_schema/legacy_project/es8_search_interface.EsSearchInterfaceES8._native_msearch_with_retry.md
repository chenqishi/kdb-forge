# es8_search_interface.EsSearchInterfaceES8._native_msearch_with_retry

## Inputs / Outputs
Inputs: one provider client and an even header/body list. ES8 native msearch(searches=..., max_concurrent_searches=2), original per-index bodies unchanged.
Outputs: positional response list; retry only timed-out/failed-shard items up to three times, retain successful items and final partial hits with explicit warning. Per-item error remains an error response; no fake success. Transport/malformed batch failures propagate for online caller's visible single-search fallback. Maintenance strict search is unchanged.

## SQL
None.
