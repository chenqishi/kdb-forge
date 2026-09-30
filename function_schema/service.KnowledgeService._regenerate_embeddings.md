# KnowledgeService._regenerate_embeddings

## Inputs
Mutable patch with optional title/content/indexes; injected embedding client.

## Outputs
Recalculates vectors for supplied text fields and index entries. Empty root text
sets its vector to null so an ES partial update cannot retain the old vector.
Embedding failures propagate before a write. Does not modify absent root fields.

## SQL
None; embedding client calls only.
