# es817_native_batch_validation_20261009.trace_connection

## Inputs / Outputs
Old ES7 HTTP boundary wrapper; allowed GET info, HEAD fixed names, POST msearch/search only, max12 reads and15s timeout. Parse response to check shard failures and record source bytes/took/inner vector instances. Do not return raw source or credential/vector text.

## SQL
None.
