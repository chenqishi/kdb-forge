# kdb.retrieval.engines.es8_client_router.IndexClientRouter

## Signature

`IndexClientRouter(self, config: Optional[Mapping[str, Any]]=None, config_path: Optional[str]=None, client_factory: Optional[Callable[[Mapping[str, Any]], Any]]=None)`

## Inputs

- `config` 或 `config_path`：ES 路由配置。支持旧的顶层 `hosts/username/password`，也支持
  `providers` + `default_provider` + `index_routes`。
- provider：`serverless`、`paas`，兼容别名 `pass`。
- `index_routes`：`{index_name: provider}`，支持 `fnmatch` 通配符。
- `client_factory`：可选测试注入函数，接收单个 provider 配置。

## Outputs

- `resolve_provider(index_name)` 返回 provider 名。
- `get_client_by_index(index_name)` 返回缓存的 Elasticsearch 8.17 client。
- 同 provider 共享一个 client；`close()` 清理连接池。

## Behavior

精确 index 路由优先，其次通配规则，最后使用 default provider。ES8 认证使用
`basic_auth`；配置中的密码/API key 不写入日志。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_client_router.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
