# RoutedLegacyEngine._build_knn_clause

## Inputs
query vector、字段、k、num_candidates、可选 pre-filter。
## Outputs
ES8 native KNN query；nested 字段使用 nested + score_mode=max，过滤条件写入 knn.filter。
## SQL
无。
