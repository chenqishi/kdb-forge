# Feedback: CRUD and Mining Boundary

- Date: 2026-09-28.
- User correction: Payoneer Olive category inference belongs to mining and is out
  of scope for this CRUD/retrieval rebuild.
- Why: the legacy shared `SearchDataInterface` mixes ingestion business rules with
  retrieval interfaces. Presence in that class does not make a rule a search feature.
- Apply: compare actual insert/search/web_search call paths, keep generic explicit
  category normalization/tree lookup/filtering, and exclude customer-specific
  inference from both implementation and missing-feature reports. Do not infer from
  marketplace/model_platform, tags, or title; do not reinterpret upstream category
  provenance. Do not modify the old mining project as part of this exclusion.
- Evidence: legacy commit `43e7059c9` (`fix(chat-qa): add reviewed import gate and
  category mapping`), `commons/schema_trans.py::trans_qa_to_search_data`, and
  `knowledge_interface_tools/search_index_data_interface.py::process_one_data`.
- Verification: offline category regressions in `tests/test_legacy_service_compat.py`.
  Method presence or parameter-name checks do not establish full HTTP or behavioral
  equivalence; keep those claims separate from the scope decision.
