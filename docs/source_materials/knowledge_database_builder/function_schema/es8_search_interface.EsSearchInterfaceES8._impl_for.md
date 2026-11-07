# EsSearchInterfaceES8._impl_for

## Inputs / Outputs
Bind one exact physical index to its routed ES8 client. Only cache after any enabled index creation/mapping guard succeeds; a failed first operation must remain retryable.

## SQL
None.

## Cached index lifecycle
For a cached binding with ensure enabled, confirm existence before each operation; if missing, invalidate creation/mapping caches and recreate the same physical name. If the existence request itself errors, log it and let actual online per-route query retry/fallback handle availability, keeping mapping guard errors strict on new bindings.
