# kdb.retrieval.ontology.service.OntologyService.resolve

## Signature

`OntologyService.resolve(self, client: str='', product: str='', name: Optional[str]=None, include_document: bool=True) -> dict`

## Inputs

client/product小写作用域编码，默认空串；name可选精确过滤（None/空串不筛选）；include_document默认true。

## Outputs

success/message/scope/fallback/request/ontology。无行200、scope=none、fallback=true、ontology=null；有行按实际client/product计算scope，fallback=(实际作用域!=请求)。include_document=true返回该行完整data_json，false返回outline；永不合并。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/retrieval/ontology/service.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
