# kdb.retrieval.ontology.repository.OntologyRepository.probe

## Signature

`OntologyRepository.probe(self, ontology_id: str) -> Optional[OntologyRow]`

## Inputs

ontology_id；失败后当前读结果。

## Outputs

get/resolve 返回行或 None；list 返回 (元数据列表,total)；insert 返回 ontology_id；UPDATE 返回 rowcount，0 交 service 区分 404/409；故障明确抛 422/503/500，不伪装空结果。

## SQL

实际表：`dops_ontology`；DDL 来源：[20261117_ontology.sql](../migrations/20261117_ontology.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
SELECT id, ontology_id, client, product, name, alias_name, description,
       status, revision, create_time, update_time, del_flag, data_json
FROM dops_ontology WHERE ontology_id = %s
```

复用完整ID查询而非仅4列，保证DELETE幂等响应所需meta/document_bytes无需额外回查；不存在None。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
