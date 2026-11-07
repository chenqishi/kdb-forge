# FromTypeCountRequest

## Inputs
POST JSON: index_name/indexName single physical name or empty/null; from_type strict nonempty string default chat_auto; start/end null or yyyy-MM-dd HH:mm:ss local seconds. Conflicting aliases/unknown fields/malformed types reject422.

## Outputs
Validated model; no input mutation, no timezone conversion. One-sided dates accepted and intentionally unused per original Java.

## SQL
None.
