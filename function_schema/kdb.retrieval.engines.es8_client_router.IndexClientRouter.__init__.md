# kdb.retrieval.engines.es8_client_router.IndexClientRouter.__init__

## Signature

`__init__(self, config: Optional[Mapping[str, Any]]=None, config_path: Optional[str]=None, client_factory: Optional[Callable[[Mapping[str, Any]], Any]]=None) -> None`

## Inputs

`config`、`config_path` 二选一；可选 `client_factory`。

## Outputs

初始化 provider、index 路由和 client 缓存；不主动创建 ES client。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_client_router.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
