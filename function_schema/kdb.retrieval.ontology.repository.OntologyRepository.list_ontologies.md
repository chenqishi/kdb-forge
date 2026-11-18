# kdb.retrieval.ontology.repository.OntologyRepository.list_ontologies

## Signature

`OntologyRepository.list_ontologies(self, client=None, product=None, status=None, q=None, deep=False, include_deleted=False, limit=DEFAULT_PAGE_SIZE, offset=0, audit_status='approved') -> Tuple[List[OntologyRow], int]`

## Inputs

client/product/status可选，空串作用域与未传不同；audit_status默认approved、None表示不筛选；q、deep、include_deleted=false、limit=100、offset=0；service先验证分页。

## Outputs

返回(元数据列表,total)，含两个状态，不加载data_json。默认audit_status=approved且排除软删；status缺省不过滤，audit_status=None仅移除审核筛选。COUNT与分页WHERE完全一致，limit默认100。故障明确抛422/503/500。

## SQL

实际表：`dops_ontology`；DDL 来源：[建表](../migrations/20261117_ontology.sql)与[审核状态迁移](../migrations/20261118_ontology_review_status.sql)及[字段改名迁移](../migrations/20261118_ontology_status_rename.sql)。仅 PRIMARY(id)、uk_ontology_id 唯一，不建业务唯一索引。

```sql
SELECT COUNT(*) AS total FROM dops_ontology WHERE {where};
SELECT ontology_id,client,product,name,alias_name,description,status,audit_status,revision,create_time,update_time,
(CASE WHEN name=%s THEN 100 WHEN JSON_CONTAINS(alias_name,JSON_QUOTE(%s)) THEN 90
 WHEN name LIKE %s ESCAPE '!' THEN 70 WHEN name LIKE %s ESCAPE '!' THEN 50 ELSE 20 END) AS q_score
FROM dops_ontology WHERE {where}
ORDER BY q_score DESC,update_time DESC,id DESC LIMIT %s OFFSET %s;
```

WHERE 按 del_flag→client→product→status→audit_status→q 顺序，未传过滤项省略，空串保留。q 包含 name/description/LOWER(CAST(alias_name AS CHAR)) 三个 OR 条件，deep 再 OR CAST(data_json AS CHAR)，均 LIKE %s ESCAPE '!'. 参数顺序：打分4个(q,q,prefix,contains)→过滤参数→关键词3个(contains,contains,lower_contains)→可选deep contains→limit→offset。无q省略打分列/参数及q_score排序；include_deleted=true且audit_status=None等全部过滤关闭时WHERE 1=1。同一读连接查总数/分页，列表不加载data_json。

连接来自共享MySQLConnector；SET NAMES utf8mb4。写方法同一连接/游标显式REPEATABLE READ，成功commit、失败rollback；1213整笔重试一次；1205/连接断开503，3140/1406/1366映射422，其它500，响应不泄露堆栈。读路径不显式commit；游标/连接独立finally关闭，连接归还池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
