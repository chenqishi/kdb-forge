# EsSearchInterfaceES8._restore_inner_embeddings

## Inputs
ES8 nested KNN hit 与已展开的文档。
## Outputs
无返回；按 `_nested.field` (indexes/image_indexes) 和offset原地恢复relative inner source的embedding。保留root/文本/metadata/未命中array条目。Unknown path/invalid offset/nonlist忽略，不将图片向量写入indexes。支持响应多个named inner sections；字段缺失时沿用旧indexes默认。
## SQL
无。
