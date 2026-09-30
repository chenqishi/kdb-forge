# LegacySearchDataInterfaceMixin._init_legacy_compat

## Inputs
Optional legacy config and service's repository/embedding attributes.
## Outputs
Initialize old public engine/embedding/config/category attributes. Similarity tool
is injected or loaded lazily by KnowledgeService, so an injected tool never needs
an unrelated legacy config to construct successfully.
## SQL
None.
