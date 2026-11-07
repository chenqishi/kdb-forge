# run

Inputs: clients, evidence path, bounded case list. Outputs: exact paired private replies and sanitized evidence incrementally, at most 105 cases /210 service HTTP requests, sequential with pacing. Recheck existing indexes/version before requests, include baseline implementation hashes, persist actual replies before independent source evaluation so an oracle failure cannot erase them. Retain failures, never silently omit. All real operations read-only; no engine/implementation/config changes. SQL: none.
