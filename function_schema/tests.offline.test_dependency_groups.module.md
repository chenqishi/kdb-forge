# tests.offline.test_dependency_groups

## Inputs

Current pyproject.toml, canonical source imports and the existing static import inspector. Distribution names are mapped explicitly from import names (for example fitz → PyMuPDF and mysql → mysql-connector-python).

## Outputs

`declared_packages(extra)` expands local project extras without importing business modules. `test_service_import_dependencies_are_declared(entrypoint, extra)` verifies four HTTP entrypoints and five mining CLI entrypoints and their conservative internal import closure against the documented installation group. `test_all_direct_import_dependencies_are_declared()` rejects any undeclared third-party import in the all group. These checks validate declarations, not installed binary compatibility, browsers, models or external services. HTTPX is declared directly in the test group for FastAPI TestClient.

The multilingual case also checks the declared NumPy compatibility range: it must accept 1.26.4 and reject 2.0.0 / 2.5.0. The retained fastText 0.9.x prediction wrapper uses np.array(..., copy=False), whose NumPy 2 semantics reject its probability-list conversion. Actual model inference is verified separately with a real model.

## SQL

No SQL or external I/O. The default offline guard remains active.

## Source

`tests/offline/test_dependency_groups.py`
