# normalize_request

## Inputs / Outputs
Copy a generated ES8 search body, remove only the top-level _source and nested inner_hits._source projection options. Preserve every query, filter, KNN budget, size, sort, score and other option; return hashable body. Never modify an actual outgoing request.

## SQL
None.
