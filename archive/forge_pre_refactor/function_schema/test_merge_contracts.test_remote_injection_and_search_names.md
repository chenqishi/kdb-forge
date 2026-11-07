# test_remote_injection_and_search_names

## Inputs
monkeypatch, injected similarity/category tools, FakeEngine/FakeEmbedding;
parameterized string/list/empty index argument (empty must reach engine as None).
## Outputs
Verify keyword/positional remote constructor, injected dedup, category filter and
new public multi/web/batch names coexist with legacy names and list index support.
## SQL
None.
