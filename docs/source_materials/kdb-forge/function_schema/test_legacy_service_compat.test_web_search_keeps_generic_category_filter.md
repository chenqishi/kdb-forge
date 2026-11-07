# test_web_search_keeps_generic_category_filter

## Inputs
Pytest `monkeypatch`, cached generic tenant category tree, category name and ID filters.

## Outputs
Asserts web search sends the combined explicit category IDs to the engine and
retains index/pagination arguments, without tenant-specific inference.

## SQL
None; offline fake engine and embedding.
