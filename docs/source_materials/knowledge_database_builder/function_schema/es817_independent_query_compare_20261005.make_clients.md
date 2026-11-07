# make_clients

Load the existing old flat ES config and new provider config; return raw HTTP clients keyed old/serverless/paas. No engine constructors, mutations or retries. Credentials never enter artifacts. Close sessions in main finally.

SQL: none.
