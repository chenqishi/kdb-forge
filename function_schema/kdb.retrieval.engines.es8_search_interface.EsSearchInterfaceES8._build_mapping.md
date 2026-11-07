# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._build_mapping

## Signature

`EsSearchInterfaceES8._build_mapping(self) -> Dict[str, Any]`

## Inputs

引擎中的向量维度配置。

## Outputs

ES8.17 `mappings` 对象；`indexes.embedding` 和 `image_indexes.embedding` 为 indexed cosine HNSW dense_vector。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
