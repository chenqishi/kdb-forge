# ReadClient.search

Inputs: actual ES8 engine named parameters restricted to index/query/size. Outputs: forward real DSL via readonly HTTP adapter unchanged, no source pruning, no query rewriting; strict single approved index and size5. SQL/side effects: read only; retain metrics in worker-local list.
