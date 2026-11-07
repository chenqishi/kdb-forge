# test_preflight_missing_auth_and_model_are_not_created

## Inputs
`monkeypatch, tmp_path`

## Outputs
Support function under the startup/preflight contract, preserving argv/cwd and explicitly simulated external boundaries.
See test_launcher_startup.module.md for exact side effects and validation scope.

## SQL
No real SQL. Config validation is local only; startup tests substitute the SQL pool before original constructor execution.
