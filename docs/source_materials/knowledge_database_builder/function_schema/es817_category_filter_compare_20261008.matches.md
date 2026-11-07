# matches

Inputs: source, expected condition groups, endpoint. Outputs: independently evaluated boolean. Groups OR, fields AND, list values any-of. Apply default del_flag=0 unless explicitly supplied; /search supplements missing audit_result=[1,2,-1]. Empty search conditions use documented QA defaults. This is a source-membership oracle, not an ES request builder; it cannot emulate tokenized text term queries. Missing fields do not match. SQL: none.
