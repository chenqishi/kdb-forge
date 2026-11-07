# build_cases

Inputs: existing read-only clients, saved category discovery. Outputs: fixed bounded request/expected-condition matrix and minimal category fixtures. Use only five predeclared existing index pairs, existing source category IDs/names, exact keyword sampling (size=1); no vectors, writes or auto-created names. Cover /search QA+segment and bounded /web_search, short and full category fields, AND/OR/list, missing and invalid names, audit/type/delete/file/default/score/synonym variations. Persist exact requests and separately expected translated category_names behavior. SQL: none.
