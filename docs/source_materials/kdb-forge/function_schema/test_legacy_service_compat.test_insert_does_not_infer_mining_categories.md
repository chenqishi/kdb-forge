# test_insert_does_not_infer_mining_categories

## Inputs
Pytest `monkeypatch`; parameter `upstream_primary` (absent or already classified).
Fake engine/embedding, cached matching tree, Payoneer Olive marketplace/tag/title hints.

## Outputs
Asserts insertion uses the default group or preserves the upstream primary category,
keeps marketplace metadata, and does not load a tree just to infer a category.

## SQL
None; offline, no HTTP/ES/embedding service requests.
