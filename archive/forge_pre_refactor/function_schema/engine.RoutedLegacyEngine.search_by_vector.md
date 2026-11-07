# RoutedLegacyEngine.search_by_vector

## Inputs
query vector、vector field、size/min_score、return_score、extra_query、目标索引。
## Outputs
按 provider 合并的 ES8 native KNN 结果列表；`return_score=True` 时返回 `(doc, score)`。
## SQL
无。
