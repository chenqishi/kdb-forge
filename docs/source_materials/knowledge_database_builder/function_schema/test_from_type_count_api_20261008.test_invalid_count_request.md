# test_invalid_count_request

## Inputs
Offline pytest parameters/real service & engine implementation; external ES/embedding doubles only.

## Outputs
Malformed time, timezone, invalid source type, union/wildcard/_all/dot/dotdot/leading exclusion or oversized/path-invalid name or unknown parameter ->422, no count/ensure/write.

## SQL
None; no real ES or service writes.
