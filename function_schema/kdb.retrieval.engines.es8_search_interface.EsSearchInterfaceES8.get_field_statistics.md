# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.get_field_statistics

## Signature

`EsSearchInterfaceES8.get_field_statistics(self, index_name: str, field_name: str, extra_query: Optional[Dict[str, Any]]=None) -> Dict[str, Any]`

## Inputs

index、field、可选额外过滤。

## Outputs

单 index 返回旧统计结果；跨 provider 请求返回可诊断错误，避免伪造全局统计。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
