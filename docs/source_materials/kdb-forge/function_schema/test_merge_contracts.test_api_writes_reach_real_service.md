# test_api_writes_reach_real_service

## Inputs
service fixture, monkeypatch, FastAPI TestClient.
## Outputs
Assert insert preserves ID/audit=2/synonyms and targets request index; modify reaches
real preparation/vector regeneration; delete/refresh target the same index.
## SQL
None; IO engine is mocked.
