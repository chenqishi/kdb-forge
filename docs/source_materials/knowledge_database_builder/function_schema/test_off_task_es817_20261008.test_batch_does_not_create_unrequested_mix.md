# test_batch_does_not_create_unrequested_mix

Historical test, superseded by test_batch_mix_initialization_keeps_target_provider after the user's 2026-10-08 correction. The only-target-creation expectation was not the legacy contract: f873a593 initialized mix and ensured it existed too. This test's strict xfail is not evidence of an ES8 regression or an actual wrong-target write. The replacement tests unchanged initialization and correct target provider/document writes. No application code changed; all creates remain mock only.
