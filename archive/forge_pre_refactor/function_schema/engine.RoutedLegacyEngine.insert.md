# RoutedLegacyEngine.insert

## Inputs
含 `_id` 和已生成向量的文档、目标索引、refresh 标志。
## Outputs
所有目标索引通过 ES8 `update(doc=..., doc_as_upsert=True)` upsert 成功返回 True。
## SQL
无。
