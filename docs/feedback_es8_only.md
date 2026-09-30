# Feedback: ES8 Only

## Preference
The user explicitly confirmed on 2026-09-30 that this project targets ES8 only.
Preserve the recently added ES8.17 CRUD, native KNN/BM25 split, index-based
PaaS/Serverless routing, and remote write API features when merging.

## Why
Legacy public method/configuration compatibility was being confused with support
for the old ES7 backend. Restoring that backend would undo the vector-search and
client-API migration the user requested.

## How To Apply
Keep runtime dependencies and requests on ES8.17; no ES7 downgrade or brute-force
vector fallback. Check both merge parents' positional constructor contracts, not
just names. Run the regression matrix in Merge_ES8_Write_API.md before calling a
merge safe. Separate client-contract tests from real ES retrieval-quality claims.
