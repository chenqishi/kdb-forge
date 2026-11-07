# test_empty_and_alias_requests

## Inputs
Offline pytest parameters/real service & engine implementation; external ES/embedding doubles only.

## Outputs
Empty/null/omitted name succeeds0 even uninitialized; valid aliases normalized without input mutation. Conflicting aliases rejected; no writes.

## SQL
None; no real ES or service writes.
