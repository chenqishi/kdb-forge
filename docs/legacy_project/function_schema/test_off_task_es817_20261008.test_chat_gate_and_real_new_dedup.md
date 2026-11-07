# test_chat_gate_and_real_new_dedup

Inputs: actual chat stage and high/accept vs mid/review/reject records with config check_duplicate True. Outputs: only accepted high hits actual new-engine search and upsert; correct stats/gates, no scripted soft-delete. SQL/side effects: mock client captures, no audit-status mutation.
