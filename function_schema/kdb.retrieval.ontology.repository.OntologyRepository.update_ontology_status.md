# kdb.retrieval.ontology.repository.OntologyRepository.update_ontology_status

## Signature

`OntologyRepository.update_ontology_status(self, ontology_id: str, revision: int, status: Optional[str]=None, review_status: Optional[str]=None) -> int`

## Inputs

ontology_id、revision；status与review_status为可选字符串/None，service保证至少一个非None且枚举合法。

## Outputs

返回实际更新行数。COALESCE保留值为None的状态，成功revision+1（同状态也增加），不重写文档；0由service回查区分404/409。至少一个非None及枚举合法性由service校验，空更新400来自service。故障明确抛422/503/500。

## SQL

实际表：`dops_ontology`；DDL 来源：[建表](../migrations/20261117_ontology.sql)与[审核状态迁移](../migrations/20261118_ontology_review_status.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
UPDATE dops_ontology SET status=COALESCE(%s,status),review_status=COALESCE(%s,review_status),
revision=revision+1,update_time=CURRENT_TIMESTAMP(3)
WHERE ontology_id=%s AND revision=%s AND del_flag=0;
```

参数status或None,review_status或None,ontology_id,revision；不修改data_json/投影，包含同状态在内每次成功revision+1；返回rowcount。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
