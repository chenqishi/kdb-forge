# scripts.services.preflight.module

## Inputs

Service name and exact business argv. Explicit absolute executable KDB_PYTHON; inherited cwd/PATH/PYTHONPATH are preserved. --check is a launcher-only first argument and is removed without invoking the canonical service module. Config pointers resolve with original cwd semantics, not relative to their containing JSON. No business import or client construction.

## Outputs

probe_module(name): presence/path and SDK version metadata, no secret values. option(argv,name,default): read original option with --name value or --name=value without mutating argv. read_config(path,role,...): validate bounded local JSON/required fields and collect safe file metadata. check(service,argv): safe runtime/config/dependency/model/auth diagnostics and errors; missing/incompatible resources fail before startup. main: print safe JSON, exit78 on check failure; on success --check returns0, otherwise os.execv same selected interpreter with canonical `-m <ENTRYPOINTS[name]>` and original business argv/cwd/env, preserving downstream process and exit semantics. Unknown/malformed original argv forwarded to original parser after required-resource checks where possible; no new business defaults.

## SQL

No SQL/ES/HTTP operations. Config fields mysql host/database/user/password only checked for presence, values never printed. Resource validity/auth/backend reachability not proven by local presence.

Runtime metadata distinguishes sys.executable, sys.prefix, sys.base_prefix and interpreter realpath; symlink target alone does not identify site-packages. Files config selection mirrors the original iterator; MinioTools missing-field defaults remain valid and are warned rather than disabled.

Canonical entrypoints: retrieval/off_task/files/multilingual use the explicit ENTRYPOINTS registry; off_task maps to kdb.entrypoints.http.tasks.app. Report entrypoint is this module name; entrypoint_source identifies its file under src/kdb/entrypoints/http. Execution is `[sys.executable, "-m", module, *business_argv]`. off_task --script-dir is the runtime config/data/log root; pipeline source availability is checked in this project/src/kdb/entrypoints/cli/mining. Default fasttext model is this project/resources/models/lid.176.ftz. Retired service names are rejected by main with unknown_service/exit 64 before imports, config reads or execution. Retrieval preflight does not require the removed upstream adapter's HTTP client; HTTPX remains a test dependency for TestClient.

## Source

`scripts/services/preflight.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
