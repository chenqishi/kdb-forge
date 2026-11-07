# assert_no_index_writes

## Inputs
Offline pytest parameters/real service & engine implementation; external ES/embedding doubles only.

## Outputs
Assert all fake providers have no create/put_mapping or CRUD calls; no changes in engine checked index keys after count.

## SQL
None; no real ES or service writes.
