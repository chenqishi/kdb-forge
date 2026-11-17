# kdb.retrieval.ontology.service.OntologyService.insert_ontology

## Signature

`OntologyService.insert_ontology(self, body: Any) -> dict`

## Inputs

完整body.data_json（object或JSON字符串），可选status=draft/active，默认active；禁止在HTTP请求外层传name/client/product等投影字段。

## Outputs

201（service返回dict）：success/message/ontology元数据，含UUID4 hex、revision=1、作用域、名称、状态、document_bytes及时间，不返回data_json。先校验status及文档，再事务判重插入、按生成ID回查；同业务键（含draft）409，细节保留已有ID/status/revision。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
