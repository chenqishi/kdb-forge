# Real legacy __main__ startup smoke

## Inputs
Temporary synthetic configs/models/auth only. Actual candidate legacy wrappers via runpy.run_path(...,run_name=__main__), inherited argv/cwd. Fake uvicorn.run imports its original string target and enters original retrieval lifespan; fake Flask.run records actual app and serve args. ES factory, SQL pool, Dify constructor, fasttext dependency and thread start boundary are substituted; real business constructors/config parsing execute. Socket/subprocess/real writes denied by the offline test audit guard.

## Outputs
Assertions for original service app routes, exact original host/port/workers/reload arguments, config parsing, actual constructor counts, no duplicate retrieval worker initialization, SQL initialization and worker/monitor registration without running their targets, model load success/missing-resource failure. Preflight checks missing SDK/config/model/auth safely, preserves argv/cwd on mocked exec, and never leaks synthetic secret values. Synthetic resources do not make real absent CSAT auth/fasttext resources ready; real check report remains separate.

## SQL
Original MySQLConnector config/pool constructor path only; pool replaced before constructor. No SQL statement or real connection is executed. Background worker/monitor target functions never execute.
