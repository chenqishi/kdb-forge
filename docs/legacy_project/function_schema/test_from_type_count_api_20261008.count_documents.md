# count_documents

## Inputs
Offline pytest parameters/real service & engine implementation; external ES/embedding doubles only.

## Outputs
External ES boundary double: capture body/query kwargs, evaluate fixed term/range filters over supplied synthetic docs; return native complete response, never connect ES.

## SQL
None; no real ES or service writes.
