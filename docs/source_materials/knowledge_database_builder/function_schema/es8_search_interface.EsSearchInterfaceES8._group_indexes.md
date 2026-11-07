# EsSearchInterfaceES8._group_indexes

## Inputs / Outputs
Normalize string/list indexes and bind every member, preserving contiguous provider groups and original A/B/C order. Enabled mapping guards remain strict.

## SQL
None.

## Requests
Bind each index exactly once per grouping call; reuse the already validated first binding without a second HEAD.
