# EsSearchInterfaceES8._build_knn_clause

## Inputs
query vector、字段、k、num_candidates、可选 ES8 pre-filter、可选 nested inner_hits。
## Outputs
ES8 native KNN query；nested 字段使用 `nested + score_mode=max`，不生成 `script_score`；过滤条件写入 `knn.filter`。
Nested inner_hits remain at nested query level; request _source includes use fully qualified dynamic nested paths (indexes.text/indexes.embedding or image_indexes.text/image_indexes.embedding), size3/namebest_index retained. Response source remains relative; field filtering is request-only, no persisted mapping/source edits.
## SQL
无。
