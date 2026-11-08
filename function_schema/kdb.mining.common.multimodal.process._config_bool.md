# kdb.mining.common.multimodal.process._config_bool

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

`src/kdb/mining/common/multimodal/process.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
