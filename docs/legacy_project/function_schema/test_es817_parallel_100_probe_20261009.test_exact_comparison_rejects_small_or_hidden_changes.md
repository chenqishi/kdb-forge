# test_exact_comparison_rejects_small_or_hidden_changes

## Inputs / Outputs
Same candidate/shape/result passes; parameterized tiny float, nested embedding, metadata, total, request and identity/order changes must fail strict equality, including changes below ordinary tolerance. Only comparator is exercised, no ES or services. SQL:none.
