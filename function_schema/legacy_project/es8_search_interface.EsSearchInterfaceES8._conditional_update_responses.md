# EsSearchInterfaceES8._conditional_update_responses

Inputs: validated provider binding, original physical indexes, raw query, ordered update fields, requests_per_second, abort/proceed. Outputs: checked response(s); Serverless uses existing PIT/full-source/CAS bulk adapter; PaaS retains native update_by_query script and original parameters. Full-source guard prevents destructive replacement of an index whose stored source is disabled or filtered; migration has rebuilt target indexes with complete stored source. Do not modify provider/name/config, broaden query, or fall back after partial failure. Errors visible to existing caller contract. No SQL. Real writes not authorized this turn.

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es8_search_interface.py`

Inputs: `self, binding: SimpleNamespace, names: Sequence[str], query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int, conflicts: str`.

Behavior / Outputs: Choose provider primitives while preserving caller contracts.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
