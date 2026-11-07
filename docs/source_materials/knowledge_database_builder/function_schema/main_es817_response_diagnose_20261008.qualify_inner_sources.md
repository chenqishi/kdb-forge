# qualify_inner_sources

Inputs: copy of actual current native KNN nested query. Outputs: same DSL with inner_hits._source.includes names qualified by that nested.path. Recurse only for diagnostic A/B request; never update engine implementation or settings. SQL/side effects: pure copy transformation, no data writes. Compare actual HTTP shard/hit/content lengths, not fake embeddings. Full outer source retained in both versions.
