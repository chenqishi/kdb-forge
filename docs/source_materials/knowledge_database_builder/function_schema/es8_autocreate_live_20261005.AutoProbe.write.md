# AutoProbe.write

## Inputs / Outputs
Replace only source-probe synthetic A document using synthetic nonzero 1024-vector. Qa/segment schema and owner marker preserved. Refresh fixture only.

## SQL
None.

## Native source / rerank verification
After fixture write use real GET source-probe and compare full payload including root/nested vectors. Record equality and dimensions only. Returned search score must be finite and nonzero to detect missing rerank inputs; synthetic unit vector is an API behavior fixture, not business relevance evaluation.
