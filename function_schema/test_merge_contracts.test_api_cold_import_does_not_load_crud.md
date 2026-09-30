# test_api_cold_import_does_not_load_crud

## Inputs
Fresh Python subprocess with legacy dependencies blocked.
## Outputs
Health and dry-run return success without importing CRUD, legacy or Elasticsearch;
unknown root exports raise AttributeError.
## SQL
None; offline subprocess.
