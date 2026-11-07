# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.insert_with_vectors

## Signature

`EsSearchInterfaceES8.insert_with_vectors(self, data: Dict[str, Any], vectors: Dict[str, List[float]]) -> bool`

## Inputs

旧兼容签名 `data, vectors`；目标使用默认 `index_name`。

文档、多个向量字段、可选 index。

## Outputs

使用 ES8 `index(document=...)` 写入成功返回 True；点号向量字段写成 nested JSON。

所有目标 index 插入成功返回 True。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
