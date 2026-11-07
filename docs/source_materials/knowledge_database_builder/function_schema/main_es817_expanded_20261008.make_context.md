# make_context

Inputs: in-memory approved ES8 config and source modules. Outputs: worker-local actual IndexClientRouter and EsSearchInterfaceES8 instance with readonly adapter injection; ensure_index_on_init=False and auto_update_mapping=False are in-memory safety overrides only. SQL/side effects: two ES8 version reads warm each worker's connections; no persisted config/ensure/old-engine access.
