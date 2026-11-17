# kdb.retrieval.ontology.repository.OntologyRepository.insert_if_absent

## Signature

`OntologyRepository.insert_if_absent(self, vd: ValidatedDocument, status: str) -> str`

## Inputs

ValidatedDocument 及 draft/active；UUID4 hex 由仓储生成并返回。

## Outputs

get/resolve 返回行或 None；list 返回 (元数据列表,total)；insert 返回 ontology_id；UPDATE 返回 rowcount，0 交 service 区分 404/409；故障明确抛 422/503/500，不伪装空结果。

## SQL

实际表：`dops_ontology`；DDL 来源：[20261117_ontology.sql](../migrations/20261117_ontology.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
SELECT ontology_id, status, revision FROM dops_ontology
WHERE client=%s AND product=%s AND name=%s AND del_flag=0 FOR UPDATE;
INSERT INTO dops_ontology
(ontology_id,client,product,name,alias_name,description,data_json,status)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s);
```

判重参数 client,product,name；插入参数 UUID4 hex,client,product,name,alias JSON,description,document JSON,status。同一事务/游标；命中未删行抛409，details含已有id/status/revision。1062仅可能ontology_id冲突，重生UUID重试一次；成功返回生成id。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
