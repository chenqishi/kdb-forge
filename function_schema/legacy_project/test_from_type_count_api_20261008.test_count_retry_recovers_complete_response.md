# test_count_retry_recovers_complete_response

## Inputs
Both mocked providers return partial shard response followed by complete native count.

## Outputs
Real HTTP/business/ES8 count retries, returns complete count only, no ensure or writes.

## SQL
None; external clients mocked.
