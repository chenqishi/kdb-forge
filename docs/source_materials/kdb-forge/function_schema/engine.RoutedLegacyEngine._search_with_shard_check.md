# RoutedLegacyEngine._search_with_shard_check

## Inputs
旧 body 形状的 search DSL，包含 `query`、`from`、`size`、`_source`、`sort`、`aggs` 等字段。

## Outputs
转换为 ES8 named search 参数后返回标准字典响应；不向 ES8 client 传递 `body=`。

## SQL
无；读取 Elasticsearch。
