# conftest.cfg

## Inputs
Optional integration config file and dependency availability.
## Outputs
Loaded config for integration tests; missing config/dependencies skip only the
integration fixture. API/offline tests must not skip because CRUD is unavailable.
## SQL
None.
