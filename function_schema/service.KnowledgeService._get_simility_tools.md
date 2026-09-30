# KnowledgeService._get_simility_tools

## Inputs
Injected/cached simility_tools and optional legacy availability.
## Outputs
Reuse configured tool or lazily build legacy SimilityTools(None); use the local
threshold fallback if legacy is unavailable. Never silently skip duplicate checking.
## SQL
None.
