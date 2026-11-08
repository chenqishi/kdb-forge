# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._apply_source_assignments

## Signature

`_apply_source_assignments(source: Mapping[str, Any], update_fields: Mapping[str, Any]) -> Dict[str, Any]`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## References

Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
