# kdb.retrieval.ontology.repository.OntologyRepository.update_status

## Signature

`OntologyRepository.update_status(self, ontology_id: str, revision: int, status: str) -> int`

## Inputs

ontology_id, revision, status。

## Outputs

get/resolve 返回行或 None；list 返回 (元数据列表,total)；insert 返回 ontology_id；UPDATE 返回 rowcount，0 交 service 区分 404/409；故障明确抛 422/503/500，不伪装空结果。

## SQL

实际表：`dops_ontology`；DDL 来源：[20261117_ontology.sql](../migrations/20261117_ontology.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
UPDATE dops_ontology SET status=%s,revision=revision+1,update_time=CURRENT_TIMESTAMP(3)
WHERE ontology_id=%s AND revision=%s AND del_flag=0;
```

参数status,ontology_id,revision；不修改data_json/投影，包含同状态在内每次成功revision+1；返回rowcount。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
