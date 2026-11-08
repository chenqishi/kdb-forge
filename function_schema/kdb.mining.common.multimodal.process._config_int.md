# kdb.mining.common.multimodal.process._config_int

## Signature

`_config_int(value: Any, default: int) -> int`

## Purpose

Parse integer config values with a safe fallback.

## Inputs

- `value`: raw config value.
- `default`: fallback integer when conversion fails.

## Outputs

- `int`: normalized config integer.

## SQL

No SQL access.

## Source

`src/kdb/mining/common/multimodal/process.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
