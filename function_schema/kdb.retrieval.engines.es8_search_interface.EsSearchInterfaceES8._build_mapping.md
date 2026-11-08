# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._build_mapping

## Signature

`_build_mapping(self) -> Dict[str, Any]`

## Inputs

引擎中的向量维度配置。

## Outputs

ES8.17 `mappings` 对象；`indexes.embedding` 和 `image_indexes.embedding` 为 indexed cosine HNSW dense_vector。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
