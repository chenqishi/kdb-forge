# test_dedup_failure_prevents_write

Inputs: real batch with check_duplicate True and actual new-engine search boundary failure. Outputs: exception propagates, no update attempted, failure stats written. SQL/side effects: offline read/failed write boundary only.
