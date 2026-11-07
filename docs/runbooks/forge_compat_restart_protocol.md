# Forge independent protocol retention

Restart assembly uses the released SearchDataInterface as the only formal business core. Earlier forge route/auth/model entry points delegate through `services/forge_compat`. The original KnowledgeRepository file is retained unchanged as a pure delegation protocol. Public KnowledgeService constructor and original update preparation methods are preserved.

Factory methods and count protocol must be checked against the original forge snapshot, not the previous candidate: ordinary factory keeps both legacy_search_config_path/search_config_path and missing config fallback; count-only factory does not initialize embedding or ensure indexes. Strict count passes original SDK flags through a forge-only ES8 subclass and reuses the published response validator. The released engine and Router bytes are unchanged.

The former added count smoke incorrectly asserted legacy-interface delegation. Restart checks the original forge native Repository contract instead; historical source test assertions remain unchanged.

Validation: compat_final.xml records 180 passes and 2 preserved historical request-count failures (old fixture supports _search but published core already uses _msearch). compat_merge_contracts.xml separately records an exploratory collection error importing the archived private _FallbackSimilityTools. This is not a full forge compatibility acceptance. All tests are offline; real backends and complete insert/retrieval workflows remain unverified.
