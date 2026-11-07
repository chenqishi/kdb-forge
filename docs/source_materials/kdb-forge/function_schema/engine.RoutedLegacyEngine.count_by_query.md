# RoutedLegacyEngine.count_by_query

## Inputs
原始单个物理 index 名、已构造的 ES query DSL，以及 `require_complete`（默认 `false`）。原样传给 ES，不添加查询条件或改写索引名；输入验证由调用方负责。
## Outputs
默认模式保留既有调用的 `int(count or 0)` 返回语义。

`require_complete=true` 时，通过 ES8 native `count(index=..., query=...)` 返回精确非负整数，超过 10,000 也不会截断。

显式设置 `ignore_unavailable=false`、`allow_no_indices=false`、`expand_wildcards=none`。只通过 router 选择 provider，不调用 `_impl_for`、建索引、更新 mapping、搜索或 embedding。

只有 `count` 为真实非负整数，且 `_shards.total > 0`、`successful == total`、`failed == 0` 时返回。缺少或无效计数/分片统计、超时、提前终止、失败信息均抛出异常；ES HTTP 或连接异常继续上抛。调用方负责转为失败响应，不能把失败当合法计数 0。
## SQL
无；底层读取 Elasticsearch。
