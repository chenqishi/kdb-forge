# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._native_msearch_with_retry

## Signature

`EsSearchInterfaceES8._native_msearch_with_retry(self, client: Any, searches: List[Dict[str, Any]]) -> Dict[str, Any]`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Inputs / Outputs

Inputs: one provider client and an even header/body list. ES8 native msearch(searches=..., max_concurrent_searches=2), original per-index bodies unchanged.
Outputs: positional response list; retry only timed-out/failed-shard items up to three times, retain successful items and final partial hits with explicit warning. Per-item error remains an error response; no fake success. Transport/malformed batch failures propagate for online caller's visible single-search fallback. Maintenance strict search is unchanged.

## SQL

None.

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
