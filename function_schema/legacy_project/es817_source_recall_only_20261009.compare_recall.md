# compare_recall

## Inputs / Outputs
Compare actual pre-fix/fixed ES8 raw subrequest candidate IDs with _index, order, score and total, merged candidate IDs/order/score/total, and source metadata/root vectors after removing only nested embedding fields. Validate every returned fixed nested vector equals the pre-fix vector at the same array offset. Ignore final business top-K IDs as an acceptance criterion because user asks ES recall only.

## SQL
None.
