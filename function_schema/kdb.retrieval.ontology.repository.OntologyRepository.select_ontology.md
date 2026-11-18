# kdb.retrieval.ontology.repository.OntologyRepository.select_ontology

## Signature

`OntologyRepository.select_ontology(self, client: str, product: str, name: Optional[str]) -> Optional[OntologyRow]`

## Inputs

client/product由service传入，公用维度为空串；name可选精确匹配。固定限制未删、启用且审核通过。

## Outputs

返回一行完整OntologyRow或None，仅del_flag=0、status=active、review_status=approved参与候选。按作用域优先级选取，待审/驳回/停用行不会阻止向上回落；不合并。故障明确抛422/503/500。

## SQL

实际表：`dops_ontology`；DDL 来源：[建表](../migrations/20261117_ontology.sql)与[审核状态迁移](../migrations/20261118_ontology_review_status.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
SELECT id,ontology_id,client,product,name,alias_name,description,status,review_status,revision,
       create_time,update_time,del_flag,data_json,
       ((client=%s AND %s!='')*2+(product=%s AND %s!='')) AS scope_rank
FROM dops_ontology WHERE del_flag=0 AND status='active' AND review_status='approved'
AND (client=%s OR client='')
AND (product=%s OR product='') [AND name=%s]
ORDER BY scope_rank DESC,(product='') DESC,update_time DESC,id DESC LIMIT 1;
```

一般参数 client,client,product,product,client,product[,name]。当 client非空且product为空，最后作用域条件改为 (product=%s OR client=%s)，对应追加 product,client；使客户行业行可回落，空product优先。只选active、approved、未删整行，绝不合并。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
