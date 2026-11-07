# main

Inputs: no arguments, exact recorded positive requests and approved existing connection configs.
Outputs: execute main then sg once with identical DSL/vector and endpoint; store private sanitized evidence under docs/reviews/main_es817_latency_20261008 without overwriting prior evidence. Summarize timing, counts and response fingerprints; explicitly excludes full API, embedding and business rerank timing from native query metrics. This is a small single-pass latency observation, not a load or QPS benchmark.
SQL/side effects: bounded reads only as above; local evidence only, no main workspace changes. Close preparation raw clients.
