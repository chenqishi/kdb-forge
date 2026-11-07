# post_checks

## Inputs / Outputs
Original /search and /web_search via actual old ASGI/business/factory/native ES8 or running old8003. Exact approved public A/private B; QA/segment, both orders and empty-only. Explicit score threshold -1; no error sentinel. Close AsyncClient.

## SQL
None.

## Native source / rerank verification
After fixture write use real GET source-probe and compare full payload including root/nested vectors. Record equality and dimensions only. Record identity/metadata validation separately from finite/nonzero rerank score validation. Running HTTP fixture stores the configured real model's TITLE embedding, so the identical query should produce a positive local rerank score. The isolated phase uses a unit vector with an identical mocked query vector. An arbitrary unit vector paired with a real query can legitimately yield segment score 0 under the unchanged old max(0, content cosine) logic; do not call that a product failure or change business scoring.
