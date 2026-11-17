# kdb.retrieval.ontology.validation.project_document

## Signature

`project_document(doc: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

已校验规范化的文档字典。

## Outputs

只返回 client、product、name、alias_name、description，不校验、不修改原文档。

## SQL

无直接 SQL。

## Source

`src/kdb/retrieval/ontology/validation.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
