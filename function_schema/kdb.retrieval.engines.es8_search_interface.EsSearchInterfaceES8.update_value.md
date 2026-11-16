# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.update_value

## Signature

`update_value(self, index_name: IndexNames, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> int`

## References

Elastic 8.17 docs-bulk/docs-update-by-query; 当前 ES8 provider 路由与响应校验。

## Inputs

索引、更新字段和 AND 条件列表；保持当前索引分组、字段赋值和冲突中止策略。

## Outputs

所有索引组成功时返回各组已校验 `updated` 之和，类型为非负整数；不使用 `total` 或额外 count 查询。零命中、空更新字段返回 0，仍表示成功。

PaaS 使用原生 update_by_query；Serverless 使用 PIT 快照和带版本保护的完整 source bulk index。保持同值写入计数，不增加 noop 优化。

版本冲突、失败条目、超时、响应不完整或传输错误均抛异常，不返回 False 或伪造成功计数。已成功写入的部分不自动回滚；发生异常时不能根据返回缺失推断实际写入数。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
