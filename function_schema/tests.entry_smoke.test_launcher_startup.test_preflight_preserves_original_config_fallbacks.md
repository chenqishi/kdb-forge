# tests.entry_smoke.test_launcher_startup.test_preflight_preserves_original_config_fallbacks

## Signature

`test_preflight_preserves_original_config_fallbacks(monkeypatch, tmp_path)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

验证文件服务继续接受省略连接字段的配置并提示默认值回退；不存在的配置文件必须失败。不启动服务、不访问 MinIO。

## Description

Inputs: synthetic pytest config/model/auth and patched ES/SQL/serve/thread boundaries.
Outputs: kdb.entrypoints.cli.generate_segments canonical service modules with unchanged business argv, cwd, route set, host/port/workers and initialization counts. Preflight execs the selected interpreter with -m and the canonical module name. No socket, subprocess or real SQL/model/LLM execution.
SQL: pool construction is replaced with a recording fixture.
Source: tests/entry_smoke/test_launcher_startup.py

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/entry_smoke/test_launcher_startup.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
