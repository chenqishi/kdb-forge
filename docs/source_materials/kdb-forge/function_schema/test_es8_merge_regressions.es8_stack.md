# es8_stack

## Inputs
pytest monkeypatch.

## Outputs
Real Service/Repository/RoutedLegacyEngine/IndexClientRouter and elasticsearch-py 8.17 clients. Only transport is replaced; records wire requests and in-memory source documents. Connections closed after test. Does not emulate or validate server-side KNN execution.

## SQL
None; offline only.
