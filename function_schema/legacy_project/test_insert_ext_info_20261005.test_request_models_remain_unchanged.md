# test_request_models_remain_unchanged

## Inputs
Current isolated service source and f873a593 original request definitions from git show.

## Outputs
All ten preexisting request classes/annotated fields/defaults/config remain equal. Only the explicitly authorized FromTypeCountRequest may be added; a new endpoint is not a mutation of original CRUD/search request models. Missing old classes still fail.

## SQL
None; AST and local git reads only.
