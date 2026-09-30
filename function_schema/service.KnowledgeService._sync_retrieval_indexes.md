# KnowledgeService._sync_retrieval_indexes

## Inputs
Mutable partial document and stored document. Called only for title/synonyms
updates with regenerate_embedding and no explicit indexes in the patch.
Index entries follow existing {text, embedding, ...} schema from _prepare_document.

## Outputs
Sets patch.indexes: removes obsolete title/synonym-derived text entries, adds
current title/synonyms, preserves custom entries and image-derived texts. A text
also present in retained synonyms/image indexes is not removed. As in insertion,
entries are identified by text; no index provenance field is introduced.
Does not mutate the stored document; vector regeneration is performed afterwards.

## SQL
None; pure in-memory preparation.
