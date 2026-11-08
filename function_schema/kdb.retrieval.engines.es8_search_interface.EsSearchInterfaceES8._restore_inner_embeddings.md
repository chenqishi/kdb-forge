# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._restore_inner_embeddings

## Signature

`_restore_inner_embeddings(hit: Dict[str, Any], doc: Dict[str, Any]) -> None`

## Inputs

ES8 nested KNN hit 与已展开的文档。

## Outputs

无返回；按 `_nested.field` (indexes/image_indexes) 和offset原地恢复relative inner source的embedding。保留root/文本/metadata/未命中array条目。Unknown path/invalid offset/nonlist忽略，不将图片向量写入indexes。支持响应多个named inner sections；字段缺失时沿用旧indexes默认。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
