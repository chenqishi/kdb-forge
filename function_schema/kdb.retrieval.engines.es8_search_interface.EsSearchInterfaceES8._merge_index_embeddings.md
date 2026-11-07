# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._merge_index_embeddings

## Signature

`EsSearchInterfaceES8._merge_index_embeddings(target: Dict[str, Any], other: Dict[str, Any]) -> None`

## Inputs

同一文档两条 BM25/native KNN 结果。

## Outputs

无返回；分别按indexes/image_indexes的text补齐缺失embedding，不覆盖已有值，不串文本和图片数组。没有可确定text映射就不猜测对应关系，保留现存数组/metadata。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
