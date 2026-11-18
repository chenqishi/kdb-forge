# kdb.retrieval.ontology.service.OntologyService.insert_ontology

## Signature

`OntologyService.insert_ontology(self, body: Any) -> dict`

## Inputs

完整body.data_json（对象或JSON对象字符串）；status=active/inactive，默认active；review_status=pending/approved/rejected，默认pending。投影字段只能来自文档，不能放在请求外层。

## Outputs

201（service返回dict）：success/message/ontology元数据，包含ID、作用域、名称、status、review_status、revision=1、document_bytes和时间，不返回data_json。先校验状态及文档，再事务判重插入并按生成ID回查；所有未软删行占业务键，同键409含已有ID、两个状态及revision。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
