# kdb.retrieval.ontology.repository.OntologyRepository.select_ontology_by_id

## Signature

`OntologyRepository.select_ontology_by_id(self, ontology_id: str) -> Optional[OntologyRow]`

## Inputs

32位小写hex ontology_id；内部读取包含未审核、停用与软删行。

## Outputs

返回含两个状态和完整文档的OntologyRow或None，包括未审核、停用、软删行；供写入及冲突判断使用，HTTP详情由service检查可见性。故障明确抛503/500。

## SQL

实际表：`dops_ontology`；DDL 来源：[建表](../migrations/20261117_ontology.sql)与[审核状态迁移](../migrations/20261118_ontology_review_status.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
SELECT id, ontology_id, client, product, name, alias_name, description,
       status, review_status, revision, create_time, update_time, del_flag, data_json
FROM dops_ontology WHERE ontology_id = %s
```

按ontology_id返回完整OntologyRow或None，JSON兼容str/bytes/已解码对象，时间为毫秒无时区；不按del_flag或审核状态过滤；HTTP详情由service检查可见性。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
