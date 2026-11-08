# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.insert_with_vectors

## Signature

`insert_with_vectors(self, data: Dict[str, Any], vectors: Dict[str, List[float]]) -> bool`

## Inputs

旧兼容签名 `data, vectors`；目标使用默认 `index_name`。

文档、多个向量字段、可选 index。

## Outputs

使用 ES8 `index(document=...)` 写入成功返回 True；点号向量字段写成 nested JSON。

所有目标 index 插入成功返回 True。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
