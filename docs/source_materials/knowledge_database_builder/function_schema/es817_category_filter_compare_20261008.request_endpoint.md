# request_endpoint

Inputs: requests session, side, endpoint, exact request. Outputs: actual response, duration, bytes, or explicit sanitized failure. Only existing-index /search or /web_search, HTTP timeout=60, no retries, no write endpoints. Reject HTTP200 error sentinels, empty IDs and duplicates; legitimate empty results allowed. Remove embeddings before evidence persistence. SQL: none.
