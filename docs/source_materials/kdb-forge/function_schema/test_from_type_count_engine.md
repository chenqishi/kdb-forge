# test_from_type_count_engine

## Inputs
真实 RoutedLegacyEngine、IndexClientRouter、Elasticsearch 8.17 官方客户端；只替换外部 Transport。
两个 provider 的合法、HTTP 错误、连接错误及不完整/畸形 count 响应。

## Outputs
41 项回归验证 literal index、原始 query、严格 native count 参数、0/超过10000计数、
分片完整性和计数类型校验，以及既有 require_complete=False 调用语义。
计数过程不调用 ensure/create/mapping/search/embedding；错误必须上抛。

## SQL
无；离线，无实际 ES 网络/写入。
