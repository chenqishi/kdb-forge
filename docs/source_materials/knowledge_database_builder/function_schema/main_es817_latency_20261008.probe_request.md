# probe_request (embedded standalone remote probe)

Inputs: in-memory approved provider credentials and one GET-root, HEAD-exact-index or POST-exact-index/_search request. Exact allowed indices mercado_local/payoneer_olive; search size<=5, profile disabled, no script/write operations.
Outputs: native response only in memory plus HTTP wall time, JSON parse time, byte length, ES took/shards and status. Reject partial/timeouts/errors, stop on first error, no automatic retries. Full source preserved; credentials and document text/vector values are not emitted.
SQL/side effects: reads only. Normal verified HTTP/S transport, proxies disabled consistently at both locations, response bounded at16MiB, timeout15s, sessions/connections closed.
