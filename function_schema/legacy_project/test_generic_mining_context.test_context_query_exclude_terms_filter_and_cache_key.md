# test_context_query_exclude_terms_filter_and_cache_key

## Inputs

- Pytest temporary directory and monkeypatch fixture.

## Outputs

- Regression assertions that excluded country terms are removed before intent summarization and that filter changes produce a distinct context cache key.

## SQL

None; chat loading is mocked.
