# Candidate service preflight

## Inputs
Service name and exact legacy argv. Explicit absolute executable KDB_PYTHON; inherited cwd/PATH/PYTHONPATH are preserved. --check is a launcher-only first argument and is removed without invoking the legacy entry. Config pointers resolve with original cwd semantics, not relative to their containing JSON. No business import or client construction.

## Outputs
probe_module(name): presence/path and SDK version metadata, no secret values. option(argv,name,default): read original option with --name value or --name=value without mutating argv. read_config(path,role,...): validate bounded local JSON/required fields and collect safe file metadata. check(service,argv): safe runtime/config/dependency/model/auth diagnostics and errors; missing/incompatible resources fail before startup. main: print safe JSON, exit78 on check failure; on success --check returns0, otherwise os.execv same selected interpreter with original script argv/cwd/env, preserving downstream process and exit semantics. Unknown/malformed original argv forwarded to original parser after required-resource checks where possible; no new business defaults.

## SQL
No SQL/ES/HTTP operations. Config fields mysql host/database/user/password only checked for presence, values never printed. Resource validity/auth/backend reachability not proven by local presence.

Runtime metadata distinguishes sys.executable, sys.prefix, sys.base_prefix and interpreter realpath; symlink target alone does not identify site-packages. FastGPT missing cwd config/config.json retains its original built-in upstream/private-default key fallback and emits a clear warning; no additional mandatory config is invented. Files config selection mirrors the original iterator; MinioTools missing-field defaults remain valid and are warned rather than disabled.
