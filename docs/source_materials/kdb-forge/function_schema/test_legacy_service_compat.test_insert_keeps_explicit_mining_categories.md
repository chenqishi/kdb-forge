# test_insert_keeps_explicit_mining_categories

## Inputs
Pytest `monkeypatch`; parameter `tree_available`; explicit upstream category with
legacy aliases and `source=model_platform`, fake engine and embedding.

## Outputs
Asserts explicit categories are normalized and retained. A matching tree builds
the primary category; an unavailable tree does not discard upstream categories.

## SQL
None; category lookup is mocked, no network or ES writes.
