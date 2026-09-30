# KnowledgeService.update

## Inputs
Document ID, partial document, optional index_name, regenerate_embedding, refresh.
Explicit indexes replaces the index list as before. Without explicit indexes,
title/synonyms changes with regeneration require reading the stored document.

## Outputs
Boolean write result. Preserves unrelated fields and caller input; refreshes
update_time. Updates both root vectors and derived indexes used by ES8 native KNN.
Missing/unreadable source when merging derived indexes raises ValueError before
writing, rather than silently erasing existing custom/image/synonym index entries.

## SQL
None; repository get/update on the same requested Elasticsearch index.
