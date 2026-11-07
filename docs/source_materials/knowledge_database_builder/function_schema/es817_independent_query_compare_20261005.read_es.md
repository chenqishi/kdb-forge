# read_es

Accept client, verb, path and optional body. Allow GET/HEAD for exact ten predeclared existing index names and cluster root; POST only exact index _search (size<=60), _count, _mget (<=40 IDs). No wildcard, unknown index, script update or mutations. Return successful complete response; reject HTTP/error/partial-shard failure. Raw search script_score is permitted only for read diagnosis. No auto-create engine path.

SQL: none.
