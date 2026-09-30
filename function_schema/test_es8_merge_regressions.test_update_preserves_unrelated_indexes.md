# test_update_preserves_unrelated_indexes

## Inputs
es8_stack and partial updates with shared title/synonym text, cleared text, changed synonyms, explicit indexes or no regeneration.

## Outputs
Unrelated custom/image entries preserved, obsolete derived entries replaced; explicit arrays remain authoritative; caller input unchanged; null vectors clear stale values.

## SQL
None; offline only.
