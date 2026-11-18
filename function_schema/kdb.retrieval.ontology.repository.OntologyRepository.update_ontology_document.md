# kdb.retrieval.ontology.repository.OntologyRepository.update_ontology_document

## Signature

`OntologyRepository.update_ontology_document(self, ontology_id: str, revision: int, vd: ValidatedDocument, status: str, audit_status: str=DEFAULT_AUDIT_STATUS) -> int`

## Inputs

ontology_id、revision、ValidatedDocument、status、audit_status（默认pending）；service先验证文档、状态和作用域不可变。

## Outputs

返回实际更新行数；文档、投影、两个状态同一乐观锁UPDATE写入，audit_status默认pending。0由service回查区分404/409；成功revision+1。故障明确抛422/503/500。

## SQL

实际表：`dops_ontology`；DDL 来源：[建表](../migrations/20261117_ontology.sql)与[审核状态迁移](../migrations/20261118_ontology_review_status.sql)及[字段改名迁移](../migrations/20261118_ontology_status_rename.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
SELECT ontology_id,status,audit_status,revision FROM dops_ontology
WHERE client=%s AND product=%s AND name=%s AND del_flag=0 AND ontology_id<>%s FOR UPDATE;
UPDATE dops_ontology SET name=%s,alias_name=%s,description=%s,data_json=%s,status=%s,audit_status=%s,
revision=revision+1,update_time=CURRENT_TIMESTAMP(3)
WHERE ontology_id=%s AND revision=%s AND del_flag=0;
```

判重参数client,product,new name,ontology_id；更新参数new name,alias JSON,description,document JSON,status,audit_status,ontology_id,revision。name可改但判重，client/product由service先校验不可变。不命中版本返回0，service回查404/409。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
