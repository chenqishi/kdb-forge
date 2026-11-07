# EsSearchInterfaceES8._ensure_index

## Inputs / Outputs
Inputs: exact index and optional client binding. Create missing index with complete native HNSW mapping; leave existing fields unchanged with auto_update_mapping false. A concurrent resource_already_exists_exception must be followed by mapping validation. Never cache unsuccessful creation or incompatible mapping. No real business/staging test writes.

## SQL
None.
