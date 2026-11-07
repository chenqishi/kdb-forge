# kdb.mining.parsing.multimodal_process._config_bool

## Signature

`_config_bool(value: Any, default: bool=False) -> bool`

## Purpose

Parse bool-like config values from Python bools, numbers, and strings.

## Inputs

- `value`: raw config value.
- `default`: fallback boolean when `value` is missing or unrecognized.

## Outputs

- `bool`: normalized config flag.

## SQL

No SQL access.

## Source

`src/kdb/mining/parsing/multimodal_process.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
