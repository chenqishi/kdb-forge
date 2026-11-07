# source_evidence

Read existing paired-response file. Select all changed-result identities plus both top1 identities and common IDs with score delta>1e-6. API dataset prefers stored dataset and is not always physical _index: resolve selected IDs by _mget only within both original requested indices, omit records absent from both old and new at a physical location. Bounded exact-index _mget in chunks<=40; no query to unapproved index. Compare full stored source and vector-field fingerprints/dimensions, business metadata/content and flags. Write sanitized comparisons; never artifact credentials, raw vectors or full records. Read latest five old Mercado records and new existence to diagnose the single count difference. Does not assert global data equivalence from sampled records.

SQL: none.
