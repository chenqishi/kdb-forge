# discover

Inputs: raw clients, preflight mappings, new output directory. Outputs: actual category path/parent/child ID aggregates, missing-category and third/fourth-level counts, source/title fixtures in the two named clients. Bounded exact-index search size<=60; terms aggregations may be truncated, retain error/sum_other_doc_count and never claim full taxonomy. Sample one existing del_flag0 document per chosen category; prefer QA audit_result1/2/-1, fallback any existing document and mark type. Read both original physical scopes, no fabricated documents. SQL: none.
