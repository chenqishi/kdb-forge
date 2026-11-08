# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._validate_vector

## Signature

`_validate_vector(self, vector: Sequence[float]) -> None`

## Inputs

待检索或写入的向量。

## Outputs

维度正确时无返回；错误时抛 `ValueError`。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
