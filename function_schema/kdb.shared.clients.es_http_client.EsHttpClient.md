# kdb.shared.clients.es_http_client.EsHttpClient

## Signature

`EsHttpClient(self, hosts: List[str], username: Optional[str]=None, password: Optional[str]=None, timeout: int=60)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

ES / OpenSearch 的裸 HTTP 客户端，提供 search / count / search_after 分页 / terms 聚合 /
_bulk 局部更新。给「不能碰 mapping 的只读脚本」和「只更新单个字段的回补脚本」共用。

原先这个类内嵌在 `data_control_tools/relabel_qa_quality_by_llm.py` 里，
`src/kdb/retrieval/maintenance/qa_export.py` 也需要它，而 relabel 那个文件顶层 import 了
`chat_qa_extract` / `quality_tools` 等重依赖（且未纳入 git），所以抽到 `commons/` 下。
relabel 脚本现在 `from kdb.shared.clients.es_http_client import EsHttpClient`，逻辑未变。

## 为什么不用 EsSearchInterface

1. `EsSearchInterface.__init__` 会 `_ensure_index`，即**建索引 / 改 mapping**——只读场景不能有这个副作用。
2. 阿里云 ES Serverless 不支持 scroll（`serverless_unsupported_exception`），只能 search_after。

## 构造

### `__init__(hosts, username=None, password=None, timeout=60)`
- `hosts` (list[str]) — 只用第一个；空列表抛 `ValueError`
- `username` / `password` — 都给才启用 basic auth
- 内置 `Retry(total=5, connect=5, read=3, backoff_factor=1.5, status_forcelist=(502,503,504))`；
  业务级 4xx 不重试，立即抛错

### `from_config(config_path, timeout=60) -> EsHttpClient`
读 `config/config_es_engine.json` 形态的 JSON：`{"hosts": [...], "username":..., "password":...}`。

## 方法

| 方法 | Inputs | Outputs |
|---|---|---|
| `search(index, body, allow_partial=False, retries=4)` | 索引名（支持 `a,b` 多索引）、完整 search body | `dict` 响应体；非 200 抛 `RuntimeError`；`_shards.failed>0` / `timed_out` 重试后仍不全抛 `PartialShardFailure` |
| `count(index, query, retries=4)` | 索引名、query 体 | `int`；分片不全同样重试后抛 `PartialShardFailure` |
| `iter_search_after(index, query, source_fields, page_size=1000, limit=None)` | `source_fields` 为 `_source` 白名单 | 迭代 `(_id, _source)` |
| `shard_failure_reason(payload)`（模块级函数） | 任意 search/count 响应体 | 结果不全的原因串，完整则 `None` |
| `terms_agg(index, query, field)` | 聚合字段（keyword） | `{bucket_key: doc_count}`，size 固定 50 |
| `bulk_update_field(index, updates, field, batch_size=200)` | `updates=[(_id, value), ...]` | `{'updated': n, 'failed': [...]}` |

## SQL

不涉及 SQL（数据源是 ES 不是 MySQL）。

## ES 读写

本模块与索引字段无关，读写哪些字段由调用方的 query / source_fields / updates 决定。
唯一的固定行为：`iter_search_after` 用 `sort: [{"_id": "asc"}]` 保证分页稳定。

## 注意

- **部分分片失败会静默丢数据**：阿里云 ES Serverless 会取消跑得慢的分片任务
  （`task_cancelled_exception`），HTTP 仍是 200，只是 `_shards.failed>0`、hits 少一个分片的量。
  `iter_search_after` 的游标只认最后一条 hit，被取消分片在这一段的文档就**永久跳过**。
  所以 `search` / `count` 默认校验 `_shards` 并重试整页（游标不前移），
  连续失败时 `iter_search_after` 把页大小折半（下限 `MIN_PAGE_SIZE=50`），到底还失败就抛错。
  **导出/对账类脚本不要传 `allow_partial=True`。**
- **不能用 scroll**：Serverless 集群会直接报 `serverless_unsupported_exception`。
- `bulk_update_field` 对 413 会把 `batch_size` 折半重试（Serverless 单请求 15MB 上限）；
  写入类调用要检查返回里的 `failed`，ES 可能**部分成功**再报错。
- `_cat/indices` 的 `docs.count` 含 nested 子文档，对账要用 `count()`。

## Source

`src/kdb/shared/clients/es_http_client.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
