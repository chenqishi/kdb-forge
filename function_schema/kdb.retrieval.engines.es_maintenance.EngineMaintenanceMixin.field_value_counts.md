# kdb.retrieval.engines.es_maintenance.EngineMaintenanceMixin.field_value_counts

## Signature

`field_value_counts(self, index_name: str, field: str, query: Dict[str, Any], size: int=10) -> Dict[str, int]`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/retrieval/engines/es_maintenance.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
