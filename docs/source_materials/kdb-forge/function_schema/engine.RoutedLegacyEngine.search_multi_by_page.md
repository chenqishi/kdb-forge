# RoutedLegacyEngine.search_multi_by_page

## Inputs
query、目标索引、size、page_num、score_threshold。
## Outputs
ES8 named `from_` 的 BM25 分页路径 `(docs, total)`；此接口不混入 KNN。
## SQL
无。
