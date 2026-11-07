# capture_sources

Inputs: read client, original public/private physical indexes, IDs, cache. Outputs: every found stored source by ID with original physical index. Batches <=40 IDs, only selected nonvector fields via URL _source_includes (the root _mget body accepts ids/docs, not root _source); errors abort rather than count as missing. API dataset is not assumed physical. Close sessions in main. SQL: none.
