# test_es8_interface.FakeClient.msearch

## Inputs / Outputs
Inputs: ES8 searches alternating headers/bodies and concurrency.
Outputs: mock native batch with positional responses through existing fake search boundary, capturing msearch call; subsearch failures become error items. No real ES writes.

## SQL
None.
