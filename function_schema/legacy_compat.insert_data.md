# LegacySearchDataInterfaceMixin.insert_data

## Inputs
旧版 `insert_data(data, check_duplicate, index_name, is_update_data, is_only_title,
basic_threshold, title_basic_threshold, refresh_imm, is_need_llm)` 参数。

## Outputs
返回 `(bool, str)`；保留 process、查重、重复软删除/拒绝和 ES 写入副作用。

## SQL
无；读写 Elasticsearch。
