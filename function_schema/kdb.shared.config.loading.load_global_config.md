# kdb.shared.config.loading.load_global_config

## Signature

`load_global_config(defaults, project_root)`

## Inputs

Existing default dictionary and the owning project root. Reads config/global_config.json under that root if it exists.

## Outputs

Deep-copies defaults, overlays the existing JSON configuration using dict.update, retains original logging and failure fallback. No network, database, or secret lookup. Extracted from _load_global_config without changing the merge order.

## SQL

None.

## Source

`src/kdb/shared/config/loading.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
