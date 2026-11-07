# test_cached_index_removed_is_created_again

## Inputs / Outputs
Real engine after known empty private was created/cached, remove that in-memory ES index, then joint search must recreate its exact physical name with HNSW mapping and retain public hit. No real writes.
## SQL
None.
