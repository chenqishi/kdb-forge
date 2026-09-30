# RoutedLegacyEngine.search_multi

## Inputs
query、目标索引、size、page_num、可选 recall_mode。
## Outputs
`(docs, total)`；默认 dual，BM25/native KNN 分路后按 `_index + _id` 合并。
## SQL
无。
