# kdb.retrieval.ontology.repository.OntologyRepository.delete_ontology

## Signature

`OntologyRepository.delete_ontology(self, ontology_id: str, revision: Optional[int]) -> int`

## Inputs

ontology_id, 可选 revision。

## Outputs

返回首次软删的实际更新行数；0由service区分已删、不存在及版本冲突。 故障明确抛422/503/500，不伪装空结果。

## SQL

实际表：`dops_ontology`；DDL 来源：[20261117_ontology.sql](../migrations/20261117_ontology.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
UPDATE dops_ontology SET del_flag=1,revision=revision+1,update_time=CURRENT_TIMESTAMP(3)
WHERE ontology_id=%s AND del_flag=0 [AND revision=%s];
```

参数ontology_id[,revision]；只软删未删行，无revision时仍限制del_flag=0。返回rowcount；重复删除和不存在由service区分。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
