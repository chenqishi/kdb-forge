# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.search_multi_by_page

## Signature

`search_multi_by_page(self, query: Dict[str, Any], index_names: IndexNames=None, size: int=10, page_num: int=1, score_threshold: Optional[float]=None) -> Tuple[List[Dict[str, Any]], int]`

## Description

分页的多组属性条件混合检索。**这条路是 `/web_search` 专用**，与线上实时检索用的
`search_multi` 是两个独立方法，互不复用。

## 调用链（唯一）

```
POST /web_search                                  knowledge_database_search_es.py:596
  -> web_remote_service                           :265
    -> SearchDataInterface.web_search_data        search_index_data_interface.py:1033
      -> engine.search_multi_by_page              es_search_interface.py:1340 (EsSearchInterfaceOri)
```

线上 Sell_Agent 走的是 `/search` -> `search_data_by_query` -> `search_multi`，**不经过本方法**。
（已与 common_v2 会话确认：全仓无 `/web_search` 调用，运行时日志里 8003 地址 23 次全是 `/search`。
注意 sell_agents 仓库里的 `web_search_enabled` 是 Tavily 联网开关，同名但无关，别当成调用方。）

## Inputs

| 参数 | 类型 | 说明 |
|---|---|---|
| `query` | Dict | `{"query": 文本, "vector": {"value": [...]}, "attribute": [条件组...]}`，`attribute` 各组之间 OR |
| `index_names` | str \| List[str] \| None | 目标索引 |
| `size` | int | 每页条数。**`web_search_data` 不传时默认 10000** |
| `page_num` | int | 页码，从 1 开始 |
| `score_threshold` | float \| None | 映射为 ES `min_score`，仅在有 `query` 或 `vector` 时生效 |

query、目标索引、size、page_num、score_threshold。

## Outputs

`Tuple[List[Dict], int]` — `(文档列表, total_num)`。每条为 `{"_id", "score", **_source}`。

**`_source` 不含任何向量字段**，由 `_PAGE_SOURCE_EXCLUDES` 排除：
`indexes.embedding`、`image_indexes.embedding`、`title_embedding`、`content_embedding`。

ES8 named `from_` 的 BM25 分页路径 `(docs, total)`；此接口不混入 KNN。

## 召回策略：只走 BM25，不做向量召回

`should` 里只有两路，都是 BM25：
- `multi_match` on `title^2` / `content^1.5` / `indexes.text`
- `match` on `synonyms_title`（boost 1.8）

**刻意不挂向量子句。** 传入的 `query["vector"]` 只做维度校验，不参与检索。

### 为什么去掉

索引里的 `dense_vector` **没有开 index**（mapping 仅 `{"type":"dense_vector","dims":1024}`，
ES 7.10 下即「存而不建索引」），所以原来的 `nested + script_score + cosineSimilarity(match_all)`
是全量暴力扫描：6 万文档 × 每条的每个 `indexes` 项 × 1024 维，每次查询重算，吃不到索引。

| 场景 | 仅 BM25 | 带向量 | 倍数 |
|---|---|---|---|
| from=0, size=10 | 39ms | 151ms | 3.9x |
| from=9000, size=50 | 14ms | 351ms | **25x** |
| from=9000, size=1000 | 11ms | 1569ms | **143x** |

**翻页越深差距越大**：BM25 能靠倒排索引廉价跳过，`script_score` 却必须无差别重算全部文档。

副作用：`script_score` 内层是 `match_all`，会把每条文档都算作命中，白白撑大结果集
（同一 query 下 n 从 6793 涨到 10000），也妨碍 BM25 的提前终止。

### 为什么不损失质量

这条路**不做本地相似度重排** —— `web_search_data` 只调 `render_multimodal_urls` 和 `score/5.0`
ES `took` 合计 1468ms -> 537ms。

需要语义召回的是线上 `/search`（`search_data_by_query` -> `search_multi`），
那条路有 dual 双路 + `inner_hits` + 本地重排，与本方法互不复用。

## 分片静默取消与拆批（可靠性）

阿里云 serverless ES 会取消部分分片的查询任务却**仍返回 HTTP 200**，线索只在响应体：

```
_shards: {total: 3, successful: 2, failed: 1,
          failures: [{shard: 0, reason: {type: "task_cancelled_exception"}}]}
hits.hits  = []      ← 空
hits.total = 9370    ← 照旧报全量
```

调用方看到的是「total=9370 但一条都没有」。**这比慢危险得多**：批量清洗/审计脚本
会把「查不到」误判成「库里没有这条」而漏处理数据，且全程无报错。

两个因素都真实存在，修法分两层：

| 层 | 现象 | 处理 |
|---|---|---|
| 硬上限 | 静置时 size=5000/10000 **必败**，重试无效 | 超过 `_SAFE_PAGE_BATCH`(500) 自动拆批 |
| 负载抖动 | 压满时 size=500 也会失败；同条请求连成功十几次后仍偶发 | `_SHARD_RETRY_TIMES`(3) 次退避重试 |

size=2000 → 4/4 成功 5.6s；size=5000 → 0/4；size=10000 → 0/4。

拆批后每批各自带重试；重试仍失败**抛 RuntimeError**，由 `search_multi_by_page` 的
except 兜成 `([], 0)` 并打 error 日志，绝不静默返回「看起来成功的空结果」。

⚠️ 排查这类问题时，**测失败率前要先静置集群、请求间留间隔**——自己的压测会污染结论。

线上 `/search` 走的 `search_multi` 用 msearch，其子请求同样不报 error、只在 `_shards` 留痕，
已加 warning 日志（size 仅 10~40，风险低且双路互为兜底，故不抛错中断检索）。

## SQL / 存储

不涉及 SQL。读 ES 索引（`payoneer_olive` 等），只读不写。
默认追加 `{"term": {"del_flag": 0}}`，除非 `attribute` 里已显式指定 `del_flag`。

字段映射（与 `search_multi` 一致）：
- `from_file_name` -> `ext_info.from_file_name.keyword`
- `category_path` / `category_ids` / `cate{1..3}_name` / `cate{1..3}_id` / `cate_name` -> 加 `primary_category.` 前缀

## 相关测试

`tests/test_dual_route_recall.py`：
- `test_search_multi_by_page_has_no_vector_clause` —— 守住「不挂 script_score」
- `test_search_multi_by_page_excludes_all_vector_fields` —— 按性质断言，挡住新增向量字段遗漏
- `test_search_multi_by_page_still_validates_vector_dimension` —— 维度校验行为不变
- `test_search_multi_keeps_vector_route_untouched` —— 守住边界，不波及线上 `search_multi`
- `test_shard_cancellation_is_not_silently_swallowed` —— 静默失败必须抛错
- `test_shard_cancellation_recovers_on_retry` —— 瞬时取消重试后恢复
- `test_large_size_is_split_into_safe_batches` —— 大 size 拆批、from 顺序推进、total 不被改写
- `test_small_size_is_not_split` / `test_batch_stops_early_when_exhausted`

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
