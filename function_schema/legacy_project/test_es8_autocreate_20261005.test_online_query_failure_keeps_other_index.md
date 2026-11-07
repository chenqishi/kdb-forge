# test_online_query_failure_keeps_other_index

## Inputs
Pytest offline fixture: real original service, real business constructor, real factory and ES8 class; mock only provider ES client and embedding/similarity service boundaries. Native mapping fixture has3 dimensions. Client tracks exact named index existence, creation payload, mapping and documents. Tests use synthetic in-memory public/private indexes only.

## Outputs
Assert missing-index creation, valid complete HNSW payload, public hit preservation and metadata/ID/positive local rerank score. Explicit ensure false must never create. Concurrent creation is validated; real mapping conflicts and forbidden creation remain errors without failed binding cache. Existing mapping put calls remain zero. No real ES writes, model calls or services started.

## SQL
None.
