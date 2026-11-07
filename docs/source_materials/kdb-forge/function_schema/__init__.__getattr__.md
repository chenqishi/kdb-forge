# kdb.__getattr__

## Inputs
Public export name: KnowledgeRepository, KnowledgeService or SearchDataInterface.
## Outputs
Lazily import/cache the requested CRUD class; unknown names raise AttributeError.
Importing kdb.api for health/dry-run must not import CRUD, ES or legacy dependencies.
## SQL
None.
