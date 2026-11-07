# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._msearch_with_shard_check

## Signature

`EsSearchInterfaceES8._msearch_with_shard_check(self, msearch_body: List[Dict[str, Any]]) -> Dict[str, Any]`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Inputs / Outputs

Inputs: alternating mapping headers/bodies with exact original indexes. Reject odd lists, invalid bodies and a single header spanning different providers.
Outputs: native batches per consecutive provider, original response order. Uses bounded native concurrency (2). Subsearches retain all original parameters and full source. Raises invalid routing/mapping and batch transport failures. Online search_multi separately provides visible independent-search fallback; this body helper preserves parameters by native execution.

## SQL

None.

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
