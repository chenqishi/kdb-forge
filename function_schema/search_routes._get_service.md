# search_routes._get_service

## Inputs

进程环境 `KDB_FORGE_CONFIG`，缺省为 `config/config_search_runtime.local.json`；运行配置中的 ES
provider 凭据不记录日志。

## Outputs

懒构建并缓存一个 `KnowledgeService`；只通过 `RoutedLegacyEngine` 使用 ES8.17 named API 和
native nested HNSW KNN。

## SQL

无。
