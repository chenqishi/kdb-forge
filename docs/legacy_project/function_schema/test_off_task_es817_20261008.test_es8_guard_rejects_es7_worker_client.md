# test_es8_guard_rejects_es7_worker_client

Inputs: actual IndexClientRouter._create_client and fake installed elasticsearch module version7.10.0. Outputs: actual guard RuntimeError before client construction, showing config switch does not fix dependency version. SQL/side effects: no client/network.
