# test_native_count_failures

## Inputs
Offline pytest parameters/real service & engine implementation; external ES/embedding doubles only.

## Outputs
Real factory/engine plus missing/error/partial/incomplete/malformed count response including contradictory failures and zero count with zero shards, top-level failures and incomplete/invalid termination flags; false0, observable logs, provider isolation and no creation. ES8 retries patched zero backoff.

## SQL
None; no real ES or service writes.
