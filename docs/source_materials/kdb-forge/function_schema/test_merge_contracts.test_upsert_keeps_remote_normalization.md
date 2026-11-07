# test_upsert_keeps_remote_normalization

## Inputs
service; parameterized valid/invalid audit_result and optional document ID.
## Outputs
Assert valid audit=2 is preserved, invalid truthy audit becomes -1, from_type is
normalized, and caller dictionary is unchanged.
## SQL
None.
