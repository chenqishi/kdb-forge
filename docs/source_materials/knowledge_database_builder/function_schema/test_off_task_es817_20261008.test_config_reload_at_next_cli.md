# test_config_reload_at_next_cli

Inputs: same fixture business config path edited to another synthetic new provider between two actual CLI calls. Outputs: second invocation freshly loads config and writes new destination; existing constructed instances not claimed hot-reloadable. SQL/side effects: tmp config only; never runtime config.
