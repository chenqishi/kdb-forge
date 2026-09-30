# Memory

- ES 8.17 mixed deployment and index routing: see [docs/ES8_Index_Routing.md](docs/ES8_Index_Routing.md).
- ES7 -> ES8.17 retrieval migration: production uses `RoutedLegacyEngine` named APIs and native HNSW KNN; old unindexed `indexes.embedding` mappings must be reindexed into a new index. See [docs/ES8_Index_Routing.md](docs/ES8_Index_Routing.md).
- Legacy service compatibility: `KnowledgeService` inherits `LegacySearchDataInterfaceMixin`; `SearchDataInterface` is exported from `kdb.crud` and `kdb.knowledge_interface_tools.search_index_data_interface`, including `insert_data`, `search_data_by_query`, and `web_search_data`. Method exposure is not proof of full HTTP/behavioral equivalence. See [docs/Architecture_Overview_Diagram.md](docs/Architecture_Overview_Diagram.md).
- Scope correction (2026-09-28): Payoneer Olive category inference belongs to mining, not CRUD/retrieval compatibility. Keep generic explicit category processing and filters; see [docs/feedback_crud_mining_boundary.md](docs/feedback_crud_mining_boundary.md).
