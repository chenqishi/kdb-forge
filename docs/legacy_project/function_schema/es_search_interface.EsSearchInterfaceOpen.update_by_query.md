# es_search_interface.EsSearchInterfaceOpen.update_by_query

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_search_interface.py`

Inputs: `self, index_name: str, query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int=500`.

Behavior / Outputs: Use the existing shared native assignment implementation.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
