# kdb.retrieval.ingestion.writes.update_data_value

## Signature

`update_data_value(self, index_name: str, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> int`

## Inputs

索引、更新字段字典、AND 条件列表。

## Outputs

原样返回 ES8 引擎确认的更新条数（非负整数，包含成功的同值写入）；0 是成功结果。引擎异常原样传播，不转换成布尔值。

## SQL

无；经 ES8 引擎写 Elasticsearch，使用原生 update_by_query 或 Serverless PIT/bulk 路径。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.update_data_value`

## Source

`src/kdb/retrieval/ingestion/writes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
