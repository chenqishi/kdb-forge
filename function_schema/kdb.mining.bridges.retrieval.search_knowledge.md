# kdb.mining.bridges.retrieval.search_knowledge

## Signature

`search_knowledge(sdi, query_variants: Sequence[str], index_names: str='wayfair', condition_dicts: Optional[List[dict]]=None, top_k: int=5) -> List[dict]`

## Description

对一条 query 的所有改写变体检索 Wayfair 知识库，合并去重后返回候选知识。
走线上同款 `SearchDataInterface.search_data_by_query`（`/search` 接口内部即调它），
保证判定口径与线上检索一致。

多路合并：`normalized` + `variants` + `keywords` + 原始 query 各检一次，
按 `_id` 去重、保留各路最高 `similarity`，按分数倒排取 top_k。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sdi | SearchDataInterface | 是 | 已初始化的检索接口 |
| query_variants | list[str] | 是 | 待检索的 query 列表（已含原文与改写） |
| index_names | str | 否 | 默认 `wayfair` |
| condition_dicts | list[dict] | 否 | 默认 `[{"audit_result":[1,2],"data_type":["qa"]}]` |
| top_k | int | 否 | 每路取回条数，默认 5 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 合并去重后的知识条目，含 `_id/title/content/similarity/hit_by`，按 similarity 倒排 |

## SQL

无（读 Elasticsearch，不读 MySQL）。索引 `wayfair`，字段 `title/content/similarity/_id/audit_result/data_type/del_flag`。

## Source

`src/kdb/mining/bridges/retrieval.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
