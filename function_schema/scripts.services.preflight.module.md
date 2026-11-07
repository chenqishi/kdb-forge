# scripts.services.preflight.module

## Inputs

Service name and exact business argv. Explicit absolute executable KDB_PYTHON; inherited cwd/PATH/PYTHONPATH are preserved. --check is a launcher-only first argument and is removed without invoking the canonical service module. Config pointers resolve with original cwd semantics, not relative to their containing JSON. No business import or client construction.

## Outputs

probe_module(name): presence/path and SDK version metadata, no secret values. option(argv,name,default): read original option with --name value or --name=value without mutating argv. read_config(path,role,...): validate bounded local JSON/required fields and collect safe file metadata. check(service,argv): safe runtime/config/dependency/model/auth diagnostics and errors; missing/incompatible resources fail before startup. main: print safe JSON, exit78 on check failure; on success --check returns0, otherwise os.execv same selected interpreter with canonical `-m kdb.services.<name>.app` and original business argv/cwd/env, preserving downstream process and exit semantics. Unknown/malformed original argv forwarded to original parser after required-resource checks where possible; no new business defaults.

## SQL

No SQL/ES/HTTP operations. Config fields mysql host/database/user/password only checked for presence, values never printed. Resource validity/auth/backend reachability not proven by local presence.

Runtime metadata distinguishes sys.executable, sys.prefix, sys.base_prefix and interpreter realpath; symlink target alone does not identify site-packages. FastGPT missing cwd config/config.json retains its original built-in upstream/private-default key fallback and emits a clear warning; no additional mandatory config is invented. Files config selection mirrors the original iterator; MinioTools missing-field defaults remain valid and are warned rather than disabled.

Canonical entrypoints: retrieval/off_task/crawler/files/multilingual/csat/fastgpt_proxy map to `kdb.services.<name>.app`. Report entrypoint is this module name; entrypoint_source identifies its file under src/kdb/services. Execution is `[sys.executable, "-m", module, *business_argv]`. off_task --script-dir is the runtime config/data/log root; pipeline source availability is checked in this project/src/kdb/mining/pipelines. Default fasttext model is this project/resources/models/lid.176.ftz.

## Source

`scripts/services/preflight.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
