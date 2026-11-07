# es8_client_router.IndexClientRouter.get_client_by_provider

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es8_client_router.py`

Inputs: `self, provider: str`.

Behavior / Outputs: Return a configured provider pool for complete routed inventory.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
