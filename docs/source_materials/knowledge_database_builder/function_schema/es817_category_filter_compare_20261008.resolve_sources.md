# resolve_sources

Inputs: actual service row and source records independently fetched from both original physical indexes. Outputs: possible source records resolved by exposed _index, stored-[PRIVATE_CREDENTIAL_REDACTED], and actual returned primary_category (not by desired filter). Same _id can exist with different categories in public/private; an unrelated same-ID copy must not cause a false violation. No candidates is unresolved; indistinguishable multiple candidates with conflicting membership remain ambiguous. SQL: none.
