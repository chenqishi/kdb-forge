# RoutedLegacyEngine._ensure_index

## Inputs
索引名。
## Outputs
无；新索引使用 `indices.create(mappings=..., settings=...)` 创建 native HNSW mapping；已存在的旧未索引向量索引抛迁移错误。
## SQL
无。
