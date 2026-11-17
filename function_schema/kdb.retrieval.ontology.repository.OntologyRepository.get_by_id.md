# kdb.retrieval.ontology.repository.OntologyRepository.get_by_id

## Signature

`OntologyRepository.get_by_id(self, ontology_id: str) -> Optional[OntologyRow]`

## Inputs

32 位小写十六进制 ontology_id；含软删行，由 service 判断可见性。

## Outputs

get/resolve 返回行或 None；list 返回 (元数据列表,total)；insert 返回 ontology_id；UPDATE 返回 rowcount，0 交 service 区分 404/409；故障明确抛 422/503/500，不伪装空结果。

## SQL

实际表：`dops_ontology`；DDL 来源：[20261117_ontology.sql](../migrations/20261117_ontology.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
SELECT id, ontology_id, client, product, name, alias_name, description,
       status, revision, create_time, update_time, del_flag, data_json
FROM dops_ontology WHERE ontology_id = %s
```

按ontology_id返回完整OntologyRow或None，JSON兼容str/bytes/已解码对象，时间为毫秒无时区；不按del_flag过滤。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
