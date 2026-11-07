# trace_old

## Inputs / Outputs
Wrap existing ES7 connection at exact readonly boundary; allow GET/HEAD/POSTsearch/msearch for known indexes only, bounded size<=80,0.5sec rate, decoded response64MiB, error/shard/timeouts observable. Never permit mapping/document/index/alias writes.

## SQL
None.
