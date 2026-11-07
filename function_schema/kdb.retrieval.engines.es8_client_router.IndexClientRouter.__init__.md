# kdb.retrieval.engines.es8_client_router.IndexClientRouter.__init__

## Signature

`IndexClientRouter.__init__(self, config: Optional[Mapping[str, Any]]=None, config_path: Optional[str]=None, client_factory: Optional[Callable[[Mapping[str, Any]], Any]]=None) -> None`

## Inputs

`config`、`config_path` 二选一；可选 `client_factory`。

## Outputs

初始化 provider、index 路由和 client 缓存；不主动创建 ES client。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_client_router.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
