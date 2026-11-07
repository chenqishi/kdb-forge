# run

## Inputs
Running local old service at exact http://127.0.0.1:8003, unchanged existing provider configuration, and existing mercado_local / payoneer_olive indices. Reuse make_clients/read_es from es817_independent_query_compare_20261005 and complete_count.

## Outputs
Validate the live OpenAPI route, twelve bounded HTTP/native _count pairs (six per provider), empty index and invalid request cases, and four original search/web smoke requests. Record counts, statuses, IDs, scores and source hashes in private evidence without credentials, document text or vectors. Each existing index is HEAD checked before search to avoid auto-create. Real localhost HTTP, no ASGI stand-in. Close every session on success/failure and preserve evidence; fail on mismatches.

## SQL / Side effects
No SQL, ES writes, server restart or configuration mutation. Native reads limited to exact existing indices, no scripts or write endpoints. Two search requests may use the service's existing embedding provider. HTTP controls do not enter an ES query.
