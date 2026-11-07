# test_retry_rotates_pit_and_preserves_source

Inputs/Outputs: Replay rotating PIT after partial-shard/timeout response, then full successful page/empty page. Expected latest PIT on retries/close, one CAS write, full source unchanged apart from del_flag. No real network.
SQL and persistent side effects: none.
