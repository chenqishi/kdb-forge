# main

## Inputs / Outputs
Require --execute and existing8.17 runtime. Isolated phase uses both providers with only in-memory synthetic routing overrides, embedding boundary replaced with synthetic nonzero fixture vector; running phase actualHTTP only Serverless with runtime routes unchanged. Before creating the running fixture, obtain TITLE's vector once via the old service's configured AliEmbedding.text2embedding; validate finite nonzero 1024 shape. Store that same vector in the fixture, record only dimensions/model call count and the cosine against the discarded unit-vector fixture for diagnosing the earlier false score check. HTTP service queries use their real embedding boundary. Create/remove only approved A/B/source-probe; save sanitized counts/errors/UUID/source hash, no credentials or vector values. No deployment/restart.

## SQL
None.
