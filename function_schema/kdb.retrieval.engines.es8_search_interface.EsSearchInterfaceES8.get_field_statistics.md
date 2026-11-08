# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.get_field_statistics

## Signature

`get_field_statistics(self, index_name: str, field_name: str, extra_query: Optional[Dict[str, Any]]=None) -> Dict[str, Any]`

## Inputs

index、field、可选额外过滤。

## Outputs

单 index 返回旧统计结果；跨 provider 请求返回可诊断错误，避免伪造全局统计。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
