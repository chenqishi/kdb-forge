# test_http_count_filters_and_dates

## Inputs
Offline pytest parameters/real service & engine implementation; external ES/embedding doubles only.

## Outputs
Parametrize both providers and default/explicit/other/empty-match source types, complete/one-sided/no/reversed dates. Assert counts, exact DSL, raw physical index, no creation/putmapping/source/embedding/search.

 Include four-digit early-year boundary input to validate canonical date serialization across projects.

## SQL
None; no real ES or service writes.
