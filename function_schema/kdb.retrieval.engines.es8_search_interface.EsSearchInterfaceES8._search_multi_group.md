# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._search_multi_group

## Signature

`_search_multi_group(self, binding: SimpleNamespace, names: List[str], query: Dict[str, Any], size: int, mode: str) -> Tuple[List[Dict[str, Any]], int]`

## Inputs / Outputs

Inputs: one validated provider binding, ordered exact index names, query, size, mode. Build independent BM25/native KNN bodies for each index with unchanged per-route budgets and filter/source.
Outputs: native msearch batches (max_concurrent_searches=2) for multiple routes; single route still uses search. Merge in original index/route order, preserve total calculation and first-score rule. For old default dual with vector, request-only excludes indexes.embedding/image_indexes.embedding, retaining title/content root vectors/text/metadata; vector inner_hits restores matched nested vectors, BM25-only retains old root-vector fallback. Text-only/nondual returns full source. Native batch and independent fallback use identical source exclusions; filters/budgets/order/query and CRUD/storage remain unchanged. Per-item error logged/skipped; successful routes and final partial-shard hits retained. Query construction/mapping errors remain observable; no maintenance changes.

## SQL

None.

无。

## Inputs

provider binding、index 列表、通用 query、size、recall mode。

## Outputs

该 provider 的去重文档和命中总数；dual 模式分别执行 BM25 与 native KNN。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
