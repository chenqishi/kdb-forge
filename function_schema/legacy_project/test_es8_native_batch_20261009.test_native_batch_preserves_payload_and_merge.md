# test_es8_native_batch_20261009.test_native_batch_preserves_payload_and_merge

## Inputs / Outputs
Inputs: real Router/engine and captured native boundary responses, parameterized vector/dual modes, same ID across indexes and overlapping routes.
Outputs: assert single HTTP batch, bounded concurrency, unchanged native KNN/filter, per-index budgets, full source, first score, identity order, vectors and unmodified caller query.

## SQL
None.

After source compatibility correction, assert dual request excludes exactly old nested-vector fields and retains root vectors; vector mode continues full source. Existing API mock response doesn't emulate filtering, so new source-specific differential tests validate actual filtered payload and old legacy helpers separately; this test remains budgets/order/parameter pass-through only.
