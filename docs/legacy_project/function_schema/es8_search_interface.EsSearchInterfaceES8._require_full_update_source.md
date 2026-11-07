# EsSearchInterfaceES8._require_full_update_source

Inputs: ES client and physical index names used for conditional writes. Outputs: success only if get_mapping returns mapping entries whose stored _source is enabled and has no includes/excludes. Raise before bulk on disabled/filtered/malformed source metadata; never claim request source=True can recover storage-side exclusion. Full-source reindex migration is an already-required target precondition. Pure metadata read, no SQL/mapping writes. Aliases may resolve several mapping entries; every actual mapping must be complete.
