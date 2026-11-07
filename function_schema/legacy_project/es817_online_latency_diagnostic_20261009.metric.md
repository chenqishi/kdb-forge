# metric (remote)

Inputs: real ES response, query vector and route identity. Reject errors/timeouts/failed or incomplete shards. Return ES took, counts, ordered identity and complete-source fingerprint, root/nested/image vector instance counts, empty-inner-hit count and unmodified business QA similarity/score fingerprint. No document content or vector values in output. Query vector in memory only, no SQL or mutations. Source=False is explicitly a diagnostic variant, never business rerank acceptance.
