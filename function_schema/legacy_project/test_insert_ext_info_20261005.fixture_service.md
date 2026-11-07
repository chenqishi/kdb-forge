# test_insert_ext_info_20261005.fixture_service

Inputs: pytest monkeypatch/tmp_path. Build real old-project SearchDataInterface, engine factory, Router and ES8 class with two in-memory clients; replace only external embedding/similarity/keyword/ES boundaries. Import actual FastAPI module without lifespan/server startup. Outputs: service, business and captured clients. No network, SQL, persistent ES or audit side effects.
