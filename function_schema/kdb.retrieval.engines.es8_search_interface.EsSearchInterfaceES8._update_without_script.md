# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._update_without_script

## Signature

`_update_without_script(self, client: Any, indexes: Sequence[str], query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int, conflicts: str) -> Dict[str, Any]`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## References

Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

Serialization uses elasticsearch.serializer.JSONSerializer (the same class exported by ES8.17 root package, identity verified locally). Import the defining module so unrelated test replacement of the root module does not hide the real serializer. This does not replace client/dependencies or relax scope.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
